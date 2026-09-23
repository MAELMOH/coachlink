import 'package:flutter/foundation.dart';

/// Codes d'erreur normalises du backend (`ARCHITECTURE.md` 8).
///
/// Le backend renvoie `{"error": {"code", "message", "details"}}`. Tout code
/// inconnu est mappe sur [ApiErrorCode.unknown] : on ne casse jamais l'app
/// parce que le back a ajoute un code.
enum ApiErrorCode {
  /// Consentements obligatoires manquants -> ecran de consentement bloquant.
  consentRequired('CONSENT_REQUIRED'),

  invalidCredentials('INVALID_CREDENTIALS'),
  tokenExpired('TOKEN_EXPIRED'),
  tokenRevoked('TOKEN_REVOKED'),
  unauthorized('UNAUTHORIZED'),
  forbidden('FORBIDDEN'),
  notFound('NOT_FOUND'),
  validationError('VALIDATION_ERROR'),
  conflict('CONFLICT'),
  rateLimited('RATE_LIMITED'),

  /// Essai termine sans abonnement -> mode lecture seule.
  subscriptionRequired('SUBSCRIPTION_REQUIRED'),
  readOnlyMode('READ_ONLY_MODE'),

  /// Lien coach-client inexistant, en pause ou revoque.
  linkNotActive('LINK_NOT_ACTIVE'),

  invitationExpired('INVITATION_EXPIRED'),
  invitationAlreadyUsed('INVITATION_ALREADY_USED'),

  serverError('SERVER_ERROR'),
  unknown('UNKNOWN');

  const ApiErrorCode(this.wireValue);

  /// Valeur telle qu'envoyee par l'API.
  final String wireValue;

  static ApiErrorCode fromWire(String? value) {
    if (value == null) {
      return ApiErrorCode.unknown;
    }
    for (final ApiErrorCode code in ApiErrorCode.values) {
      if (code.wireValue == value) {
        return code;
      }
    }
    return ApiErrorCode.unknown;
  }
}

/// Erreur applicative unique manipulee par toute la couche presentation.
///
/// Les erreurs reseau/transport sont converties ici aussi, pour que l'UI n'ait
/// jamais a connaitre `DioException`.
@immutable
class ApiError implements Exception {
  const ApiError({
    required this.code,
    required this.message,
    this.details = const <String, Object?>{},
    this.statusCode,
    this.rawCode,
  });

  /// Erreur de transport : pas de reseau, DNS, socket fermee.
  const ApiError.network([String? message])
      : code = ApiErrorCode.unknown,
        message = message ?? 'network_unreachable',
        details = const <String, Object?>{},
        statusCode = null,
        rawCode = 'NETWORK_UNREACHABLE';

  const ApiError.timeout()
      : code = ApiErrorCode.unknown,
        message = 'timeout',
        details = const <String, Object?>{},
        statusCode = null,
        rawCode = 'TIMEOUT';

  /// Le certificat presente ne correspond a aucune empreinte epinglee.
  const ApiError.certificatePinning()
      : code = ApiErrorCode.unknown,
        message = 'certificate_pinning_failure',
        details = const <String, Object?>{},
        statusCode = null,
        rawCode = 'CERTIFICATE_PINNING_FAILURE';

  final ApiErrorCode code;
  final String message;
  final Map<String, Object?> details;
  final int? statusCode;

  /// Code brut recu, conserve meme quand [code] vaut `unknown`.
  final String? rawCode;

  bool get isNetworkFailure => rawCode == 'NETWORK_UNREACHABLE';
  bool get isTimeout => rawCode == 'TIMEOUT';
  bool get isPinningFailure => rawCode == 'CERTIFICATE_PINNING_FAILURE';

  /// Vrai si l'operation a une chance d'aboutir plus tard : c'est ce qui
  /// decide si la file de synchronisation garde l'operation ou la jette.
  bool get isRetryable {
    if (isNetworkFailure || isTimeout) {
      return true;
    }
    if (code == ApiErrorCode.rateLimited || code == ApiErrorCode.serverError) {
      return true;
    }
    final int? status = statusCode;
    return status != null && status >= 500;
  }

  /// Vrai si l'erreur vient d'une donnee que le client a produite : rejouer
  /// a l'identique ne changera rien, l'operation doit sortir de la file.
  bool get isPermanentClientFailure {
    final int? status = statusCode;
    if (status != null && status >= 400 && status < 500) {
      return code != ApiErrorCode.rateLimited;
    }
    return false;
  }

  /// Parse le corps `{"error": {...}}` decrit en `ARCHITECTURE.md` 8.
  static ApiError fromResponseBody(Object? body, {int? statusCode}) {
    if (body is Map) {
      final Object? error = body['error'];
      if (error is Map) {
        final Object? rawDetails = error['details'];
        return ApiError(
          code: ApiErrorCode.fromWire(error['code'] as String?),
          message: (error['message'] as String?) ?? 'unknown_error',
          details: rawDetails is Map
              ? Map<String, Object?>.from(rawDetails)
              : const <String, Object?>{},
          statusCode: statusCode,
          rawCode: error['code'] as String?,
        );
      }
    }
    return ApiError(
      code: _codeForStatus(statusCode),
      message: 'unexpected_response',
      statusCode: statusCode,
    );
  }

  static ApiErrorCode _codeForStatus(int? status) {
    switch (status) {
      case 401:
        return ApiErrorCode.unauthorized;
      case 403:
        return ApiErrorCode.forbidden;
      case 404:
        return ApiErrorCode.notFound;
      case 409:
        return ApiErrorCode.conflict;
      case 422:
        return ApiErrorCode.validationError;
      case 429:
        return ApiErrorCode.rateLimited;
      default:
        if (status != null && status >= 500) {
          return ApiErrorCode.serverError;
        }
        return ApiErrorCode.unknown;
    }
  }

  @override
  String toString() =>
      'ApiError(${rawCode ?? code.wireValue}, status: $statusCode, $message)';

  @override
  bool operator ==(Object other) =>
      other is ApiError &&
      other.code == code &&
      other.message == message &&
      other.statusCode == statusCode &&
      other.rawCode == rawCode;

  @override
  int get hashCode => Object.hash(code, message, statusCode, rawCode);
}
