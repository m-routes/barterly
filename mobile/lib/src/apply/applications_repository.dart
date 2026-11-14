import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/apply/application.dart';
import 'package:dio/dio.dart';

/// Applying, listing and withdrawing, over the API.
class ApplicationsRepository {
  new(this._dio);

  final Dio _dio;

  /// Throws [ApiError]; a 422 `application_blocked` carries the reasons
  /// (read them with [blockedReasons]).
  Future<Application> apply(String gigId, Map<String, Object?> body) =>
      guardApi(() async {
        final response = await _dio.post<Map<String, Object?>>(
          '/api/v1/gigs/$gigId/applications/',
          data: body,
        );
        return Application.fromJson(response.data!);
      });

  Future<List<Application>> mine() => guardApi(() async {
    final response = await _dio.get<Object?>('/api/v1/applications/mine/');
    final data = response.data;
    // Unpaginated today; accept a paginated body too.
    final items = switch (data) {
      final List<Object?> list => list,
      final Map<String, Object?> page => (page['results'] as List?) ?? const [],
      _ => const <Object?>[],
    };
    return [
      for (final item in items)
        if (item is Map<String, Object?>) Application.fromJson(item),
    ];
  });

  Future<Application> withdraw(String id, {String reason = ''}) =>
      guardApi(() async {
        final response = await _dio.post<Map<String, Object?>>(
          '/api/v1/applications/$id/withdraw/',
          data: {'reason': reason},
        );
        return Application.fromJson(response.data!);
      });
}

/// Uploads one file: ask the API for a signed URL, PUT the bytes to Cloud
/// Storage, then confirm (backend apps/media/views.py).
class MediaUploader {
  /// [_storage] sends the PUT. It must not carry the API's auth header: the
  /// signed URL is the credential.
  new({required this._api, required this._storage});

  final Dio _api;
  final Dio _storage;

  static String mediaKind(AttachmentKind kind) => switch (kind) {
    AttachmentKind.photo => 'photo',
    AttachmentKind.video => 'video',
    _ => 'document',
  };

  /// Returns the confirmed media id.
  Future<String> upload({
    required AttachmentKind kind,
    required String contentType,
    required List<int> bytes,
    void Function(double progress)? onProgress,
  }) => guardApi(() async {
    final ticket = await _api.post<Map<String, Object?>>(
      '/api/v1/media/upload-url/',
      data: {
        'kind': mediaKind(kind),
        'content_type': contentType,
        'size_bytes': bytes.length,
      },
    );
    final body = ticket.data!;
    final mediaId = body['media_id']! as String;
    final headers = (body['headers'] as Map?)?.cast<String, Object?>() ?? {};
    await _storage.request<void>(
      body['upload_url']! as String,
      data: Stream.fromIterable([bytes]),
      options: Options(
        method: body['method'] as String? ?? 'PUT',
        headers: {...headers, Headers.contentLengthHeader: bytes.length},
        // Exactly the signed headers: no JSON content type added by Dio.
        contentType: headers['Content-Type'] as String? ?? contentType,
      ),
      onSendProgress: onProgress == null
          ? null
          : (sent, total) => onProgress(total <= 0 ? 0 : sent / total),
    );
    await _confirm(mediaId);
    return mediaId;
  });

  Future<void> _confirm(String mediaId) async {
    for (var attempt = 0; ; attempt++) {
      try {
        await _api.post<Object?>(
          '/api/v1/media/confirm/',
          data: {'media_id': mediaId},
        );
        return;
      } on DioException catch (error) {
        // 409: storage hasn't made the file visible yet. Confirm is safe to
        // repeat, so try a couple more times.
        if (error.response?.statusCode == 409 && attempt < 2) {
          await Future<void>.delayed(
            Duration(milliseconds: 500 * (attempt + 1)),
          );
          continue;
        }
        rethrow;
      }
    }
  }
}
