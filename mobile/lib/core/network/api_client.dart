import 'package:dio/dio.dart';

import '../error/api_error.dart';
import 'auth_interceptor.dart';
import 'error_interceptor.dart';

/// Page de resultats (pagination cursor-based, ARCHITECTURE.md 8).
class Paginated<T> {
  const Paginated({required this.items, this.nextCursor});

  final List<T> items;
  final String? nextCursor;

  bool get hasMore => nextCursor != null;
}

/// Facade HTTP de l'application.
///
/// Toute la couche `data` passe par ici : elle ne connait ni `dio` ni
/// `DioException`, seulement [ApiError]. C'est aussi le point de substitution
/// unique pour les tests (un seul provider a surcharger).
class ApiClient {
  ApiClient(this._dio);

  final Dio _dio;

  /// Expose l'instance sous-jacente pour les cas rares (upload multipart avec
  /// suivi de progression). A eviter ailleurs.
  Dio get raw => _dio;

  Future<Map<String, Object?>> get(
    String path, {
    Map<String, Object?>? query,
    bool anonymous = false,
  }) async {
    final Response<dynamic> response = await _send(
      () => _dio.get<dynamic>(
        path,
        queryParameters: query,
        options: _options(anonymous: anonymous),
      ),
    );
    return _asMap(response.data);
  }

  Future<List<Map<String, Object?>>> getList(
    String path, {
    Map<String, Object?>? query,
    bool anonymous = false,
  }) async {
    final Response<dynamic> response = await _send(
      () => _dio.get<dynamic>(
        path,
        queryParameters: query,
        options: _options(anonymous: anonymous),
      ),
    );
    final Object? data = response.data;
    if (data is List) {
      return data.map(_asMap).toList(growable: false);
    }
    final Map<String, Object?> map = _asMap(data);
    final Object? items = map['items'];
    if (items is List) {
      return items.map(_asMap).toList(growable: false);
    }
    return const <Map<String, Object?>>[];
  }

  Future<Paginated<Map<String, Object?>>> getPage(
    String path, {
    Map<String, Object?>? query,
    String? cursor,
    int limit = 50,
  }) async {
    final Map<String, Object?> merged = <String, Object?>{
      ...?query,
      'limit': limit,
      if (cursor != null) 'cursor': cursor,
    };
    final Map<String, Object?> body = await get(path, query: merged);
    final Object? items = body['items'];
    return Paginated<Map<String, Object?>>(
      items: items is List
          ? items.map(_asMap).toList(growable: false)
          : const <Map<String, Object?>>[],
      nextCursor: body['next_cursor'] as String?,
    );
  }

  /// [idempotencyKey] : **doit** provenir de la file de synchronisation, qui la
  /// persiste. En generer une ici produirait un doublon serveur a chaque rejeu
  /// (voir `ARCHITECTURE.md` 8, header `Idempotency-Key`).
  Future<Map<String, Object?>> post(
    String path, {
    Object? body,
    Map<String, Object?>? query,
    String? idempotencyKey,
    bool anonymous = false,
  }) async {
    final Response<dynamic> response = await _send(
      () => _dio.post<dynamic>(
        path,
        data: body,
        queryParameters: query,
        options: _options(
          anonymous: anonymous,
          idempotencyKey: idempotencyKey,
        ),
      ),
    );
    return _asMap(response.data);
  }

  Future<Map<String, Object?>> patch(
    String path, {
    Object? body,
    String? idempotencyKey,
  }) async {
    final Response<dynamic> response = await _send(
      () => _dio.patch<dynamic>(
        path,
        data: body,
        options: _options(idempotencyKey: idempotencyKey),
      ),
    );
    return _asMap(response.data);
  }

  Future<void> delete(String path, {String? idempotencyKey}) async {
    await _send(
      () => _dio.delete<dynamic>(
        path,
        options: _options(idempotencyKey: idempotencyKey),
      ),
    );
  }

  Options _options({bool anonymous = false, String? idempotencyKey}) {
    return Options(
      extra: <String, Object?>{
        if (anonymous) AuthInterceptor.skipAuthKey: true,
      },
      headers: <String, Object?>{
        if (idempotencyKey != null) 'Idempotency-Key': idempotencyKey,
      },
    );
  }

  Future<Response<dynamic>> _send(
    Future<Response<dynamic>> Function() request,
  ) async {
    try {
      return await request();
    } on DioException catch (error) {
      throw ErrorInterceptor.toApiError(error);
    } on ApiError {
      rethrow;
    } catch (error) {
      throw asApiError(error);
    }
  }

  static Map<String, Object?> _asMap(Object? value) {
    if (value is Map) {
      return Map<String, Object?>.from(value);
    }
    return <String, Object?>{};
  }
}
