import 'dart:io';

import 'package:dio/dio.dart';

import '../error/api_error.dart';

/// Convertit toute `DioException` en [ApiError] normalisee.
///
/// Objectif : aucune couche au-dessus du reseau ne doit importer `dio`.
class ErrorInterceptor extends Interceptor {
  const ErrorInterceptor();

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) {
    handler.reject(
      DioException(
        requestOptions: err.requestOptions,
        response: err.response,
        type: err.type,
        error: toApiError(err),
        stackTrace: err.stackTrace,
      ),
    );
  }

  static ApiError toApiError(DioException err) {
    // Deja converti par un interceptor precedent.
    final Object? existing = err.error;
    if (existing is ApiError) {
      return existing;
    }

    switch (err.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
        return const ApiError.timeout();
      case DioExceptionType.connectionError:
        return const ApiError.network();
      case DioExceptionType.badCertificate:
        return const ApiError.certificatePinning();
      case DioExceptionType.cancel:
        return const ApiError(
          code: ApiErrorCode.unknown,
          message: 'request_cancelled',
          rawCode: 'REQUEST_CANCELLED',
        );
      case DioExceptionType.badResponse:
      case DioExceptionType.unknown:
        break;
    }

    if (existing is HandshakeException || existing is TlsException) {
      return const ApiError.certificatePinning();
    }
    if (existing is SocketException) {
      return const ApiError.network();
    }

    final Response<dynamic>? response = err.response;
    if (response == null) {
      return const ApiError.network();
    }
    return ApiError.fromResponseBody(
      response.data,
      statusCode: response.statusCode,
    );
  }
}

/// Extrait l'[ApiError] d'une exception levee par la couche reseau.
ApiError asApiError(Object error) {
  if (error is ApiError) {
    return error;
  }
  if (error is DioException) {
    return ErrorInterceptor.toApiError(error);
  }
  return ApiError(
    code: ApiErrorCode.unknown,
    message: error.toString(),
    rawCode: 'CLIENT_EXCEPTION',
  );
}
