import 'dart:async';

import 'package:dio/dio.dart';

import '../error/api_error.dart';
import '../storage/secure_store.dart';
import 'error_interceptor.dart';

/// Contrat de rafraichissement, injecte pour rester testable sans backend.
abstract class TokenRefresher {
  /// Echange le refresh token contre un nouveau couple de jetons.
  /// Doit lever une [ApiError] si le refresh est refuse.
  Future<AuthTokens> refresh(String refreshToken);
}

/// Raisons pour lesquelles la session est invalidee.
enum SessionEndReason { refreshRejected, refreshMissing, loggedOut }

/// Attache le jeton d'acces et rejoue une requete apres rafraichissement.
///
/// Points de conception :
/// - **Single-flight** : plusieurs 401 concurrents ne declenchent qu'un seul
///   appel de refresh ; les autres attendent le meme `Future`.
/// - **Une seule tentative par requete** : un marqueur sur `RequestOptions.extra`
///   empeche une boucle infinie si le nouveau jeton est refuse a son tour.
/// - Le refresh rotatif consomme le jeton precedent : il ne doit donc jamais
///   etre joue deux fois en parallele, sous peine d'auto-revocation.
class AuthInterceptor extends Interceptor {
  AuthInterceptor({
    required TokenStore tokenStore,
    required TokenRefresher refresher,
    required Dio retryClient,
    required void Function(SessionEndReason reason) onSessionEnded,
  })  : _tokenStore = tokenStore,
        _refresher = refresher,
        _retryClient = retryClient,
        _onSessionEnded = onSessionEnded;

  final TokenStore _tokenStore;
  final TokenRefresher _refresher;
  final Dio _retryClient;
  final void Function(SessionEndReason reason) _onSessionEnded;

  Future<AuthTokens>? _inFlightRefresh;

  /// Marque une requete comme n'ayant pas besoin de jeton (login, register,
  /// acceptation d'invitation par code).
  static const String skipAuthKey = 'coachlink.skip_auth';
  static const String retriedKey = 'coachlink.auth_retried';

  static Options get anonymous =>
      Options(extra: const <String, Object?>{skipAuthKey: true});

  @override
  Future<void> onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    if (options.extra[skipAuthKey] == true) {
      handler.next(options);
      return;
    }

    AuthTokens? tokens = await _tokenStore.read();
    if (tokens == null) {
      handler.next(options);
      return;
    }

    // Rafraichissement proactif : evite un aller-retour 401 previsible.
    if (tokens.isExpired) {
      try {
        tokens = await _refreshOnce(tokens.refreshToken);
      } on ApiError catch (error) {
        handler.reject(
          DioException(requestOptions: options, error: error),
          true,
        );
        return;
      }
    }

    options.headers['Authorization'] = 'Bearer ${tokens.accessToken}';
    handler.next(options);
  }

  @override
  Future<void> onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    final RequestOptions options = err.requestOptions;
    final bool isAuthFailure = err.response?.statusCode == 401;
    final bool alreadyRetried = options.extra[retriedKey] == true;
    final bool skipsAuth = options.extra[skipAuthKey] == true;

    if (!isAuthFailure || alreadyRetried || skipsAuth) {
      handler.next(err);
      return;
    }

    final AuthTokens? current = await _tokenStore.read();
    if (current == null) {
      _onSessionEnded(SessionEndReason.refreshMissing);
      handler.next(err);
      return;
    }

    final AuthTokens refreshed;
    try {
      refreshed = await _refreshOnce(current.refreshToken);
    } on ApiError catch (error) {
      handler.reject(DioException(requestOptions: options, error: error), true);
      return;
    }

    options.extra[retriedKey] = true;
    options.headers['Authorization'] = 'Bearer ${refreshed.accessToken}';

    try {
      final Response<dynamic> response =
          await _retryClient.fetch<dynamic>(options);
      handler.resolve(response);
    } on DioException catch (retryError) {
      handler.next(retryError);
    }
  }

  Future<AuthTokens> _refreshOnce(String refreshToken) {
    final Future<AuthTokens>? pending = _inFlightRefresh;
    if (pending != null) {
      return pending;
    }

    final Future<AuthTokens> future = _performRefresh(refreshToken);
    _inFlightRefresh = future;
    return future.whenComplete(() => _inFlightRefresh = null);
  }

  Future<AuthTokens> _performRefresh(String refreshToken) async {
    try {
      final AuthTokens tokens = await _refresher.refresh(refreshToken);
      await _tokenStore.save(tokens);
      return tokens;
    } catch (error) {
      final ApiError apiError = asApiError(error);
      // Un refresh refuse par le serveur est definitif : la session est morte.
      // Un simple probleme reseau ne doit PAS deconnecter l'utilisateur, sinon
      // on le jette dehors des qu'il entre dans une salle sans reseau.
      if (!apiError.isRetryable) {
        await _tokenStore.clear();
        _onSessionEnded(SessionEndReason.refreshRejected);
      }
      throw apiError;
    }
  }
}
