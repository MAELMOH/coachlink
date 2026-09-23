import 'dart:io';

import 'package:dio/dio.dart';
import 'package:dio/io.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../config/app_config.dart';
import '../error/api_error.dart';
import '../session/session_event_bus.dart';
import '../storage/secure_store.dart';
import 'api_client.dart';
import 'auth_interceptor.dart';
import 'certificate_pinning.dart';
import 'error_interceptor.dart';

final Provider<AppConfig> appConfigProvider = Provider<AppConfig>(
  (Ref ref) => AppConfig.fromEnvironment(),
);

/// Dio « nu » : pinning + erreurs normalisees, **sans** [AuthInterceptor].
///
/// Sert a deux choses qui ne doivent surtout pas re-declencher la chaine
/// d'authentification : l'appel de refresh lui-meme, et le rejeu d'une requete
/// apres refresh.
final Provider<Dio> bareDioProvider = Provider<Dio>((Ref ref) {
  return buildDio(ref.watch(appConfigProvider));
});

final Provider<TokenRefresher> tokenRefresherProvider =
    Provider<TokenRefresher>((Ref ref) {
  return HttpTokenRefresher(ref.watch(bareDioProvider));
});

/// Dio complet utilise par toute l'application.
final Provider<Dio> dioProvider = Provider<Dio>((Ref ref) {
  final AppConfig config = ref.watch(appConfigProvider);
  final Dio dio = buildDio(config);
  final SessionEventBus bus = ref.watch(sessionEventBusProvider);

  dio.interceptors.insert(
    0,
    AuthInterceptor(
      tokenStore: ref.watch(tokenStoreProvider),
      refresher: ref.watch(tokenRefresherProvider),
      retryClient: ref.watch(bareDioProvider),
      onSessionEnded: bus.notifySessionEnded,
    ),
  );

  ref.onDispose(dio.close);
  return dio;
});

/// Point de substitution unique pour les tests : surcharger ce provider suffit
/// a simuler n'importe quel comportement serveur, y compris l'absence de reseau.
final Provider<ApiClient> apiClientProvider = Provider<ApiClient>(
  (Ref ref) => ApiClient(ref.watch(dioProvider)),
);

/// Construit un `Dio` configure (timeouts, JSON, certificate pinning).
Dio buildDio(AppConfig config) {
  final Dio dio = Dio(
    BaseOptions(
      baseUrl: config.apiBaseUrl,
      connectTimeout: config.connectTimeout,
      receiveTimeout: config.receiveTimeout,
      sendTimeout: config.receiveTimeout,
      contentType: Headers.jsonContentType,
      responseType: ResponseType.json,
      // On veut lire le corps `{"error": {...}}` des reponses 4xx/5xx
      // plutot que de recevoir une exception opaque.
      validateStatus: (int? status) => status != null && status < 400,
    ),
  );

  dio.httpClientAdapter = _pinnedAdapter(config);
  dio.interceptors.add(const ErrorInterceptor());
  return dio;
}

IOHttpClientAdapter _pinnedAdapter(AppConfig config) {
  final SpkiPinValidator validator = SpkiPinValidator(config.spkiPins);
  final bool enforce = config.isPinningEnabled;

  assert(
    !enforce || validator.hasBackupPin,
    'Certificate pinning actif avec une seule empreinte : une rotation de '
    'certificat mettrait hors service tout le parc installe. Fournissez au '
    'moins une empreinte de secours via --dart-define=COACHLINK_SPKI_PINS.',
  );

  return IOHttpClientAdapter(
    validateCertificate: (X509Certificate? certificate, String host, int port) {
      if (!enforce) {
        // Pinning desactive (dev/debug/tests) : on laisse la validation de la
        // chaine par defaut faire son travail.
        return true;
      }
      if (certificate == null) {
        return false;
      }
      return validator.isTrusted(certificate);
    },
  );
}

/// Rafraichissement via `POST /auth/refresh` (refresh rotatif, ARCHITECTURE.md 2.2).
class HttpTokenRefresher implements TokenRefresher {
  const HttpTokenRefresher(this._dio);

  final Dio _dio;

  @override
  Future<AuthTokens> refresh(String refreshToken) async {
    try {
      final Response<dynamic> response = await _dio.post<dynamic>(
        '/auth/refresh',
        data: <String, Object?>{'refresh_token': refreshToken},
        options: AuthInterceptor.anonymous,
      );
      return parseTokens(response.data);
    } on DioException catch (error) {
      throw ErrorInterceptor.toApiError(error);
    }
  }

  /// Format attendu : `{access_token, refresh_token, expires_in}`.
  static AuthTokens parseTokens(Object? data) {
    if (data is! Map) {
      throw const ApiError(
        code: ApiErrorCode.unknown,
        message: 'malformed_token_response',
        rawCode: 'MALFORMED_TOKEN_RESPONSE',
      );
    }
    final Object? access = data['access_token'];
    final Object? refresh = data['refresh_token'];
    if (access is! String || refresh is! String) {
      throw const ApiError(
        code: ApiErrorCode.unknown,
        message: 'malformed_token_response',
        rawCode: 'MALFORMED_TOKEN_RESPONSE',
      );
    }
    final Object? expiresIn = data['expires_in'];
    return AuthTokens(
      accessToken: access,
      refreshToken: refresh,
      accessTokenExpiresAt: expiresIn is num
          ? DateTime.now().toUtc().add(Duration(seconds: expiresIn.toInt()))
          : null,
    );
  }
}
