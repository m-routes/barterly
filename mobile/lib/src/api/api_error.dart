import 'package:dio/dio.dart';

/// Any API failure, in the backend's shape `{code, message, details}`
/// (backend/apps/common/exceptions.py), plus the status and request id.
///
/// Network failures have status 0 and code `network_error`.
class ApiError implements Exception {
  const new({
    required this.status,
    required this.code,
    required this.message,
    this.details = const {},
    this.requestId,
  });

  factory fromDio(DioException error) {
    final response = error.response;
    if (response == null) {
      return const ApiError(
        status: 0,
        code: 'network_error',
        message: 'You seem to be offline. Check your connection and try again.',
      );
    }
    final requestId = response.headers.value('x-request-id');
    final data = response.data;
    if (data is Map && data['code'] is String && data['message'] is String) {
      final details = data['details'];
      return ApiError(
        status: response.statusCode ?? 0,
        code: data['code'] as String,
        message: data['message'] as String,
        details: details is Map ? Map<String, Object?>.from(details) : const {},
        requestId: requestId,
      );
    }
    final status = response.statusCode ?? 0;
    return ApiError(
      status: status,
      code: status >= 500 ? 'server_error' : 'http_error',
      message: 'Something went wrong. Try again.',
      requestId: requestId,
    );
  }

  final int status;
  final String code;
  final String message;
  final Map<String, Object?> details;
  final String? requestId;

  bool get isValidation => status == 400 && code == 'validation_error';
  bool get isUnauthorized => status == 401;

  /// One message per field of a validation error (`non_field_errors` → root).
  Map<String, String> get fieldErrors {
    if (!isValidation) return const {};
    final result = <String, String>{};
    for (final MapEntry(:key, :value) in details.entries) {
      final message = switch (value) {
        final List<Object?> list => list.whereType<String>().firstOrNull,
        final String text => text,
        _ => null,
      };
      if (message == null) continue;
      result[key == 'non_field_errors' ? 'root' : key] = message;
    }
    return result;
  }

  /// Safe to show a person; server errors carry the reference for support.
  String get userMessage => status >= 500 && requestId != null
      ? '$message (Reference: $requestId)'
      : message;

  @override
  String toString() => 'ApiError($status, $code, $message)';
}

/// Runs [call] and turns Dio failures into [ApiError].
Future<T> guardApi<T>(Future<T> Function() call) async {
  try {
    return await call();
  } on DioException catch (error) {
    if (error.error is ApiError) throw error.error! as ApiError;
    throw ApiError.fromDio(error);
  }
}
