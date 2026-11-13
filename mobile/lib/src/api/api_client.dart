import 'package:barterly/src/api/auth_interceptor.dart';
import 'package:barterly/src/api/token_store.dart';
import 'package:dio/dio.dart';

BaseOptions _options(String baseUrl) => BaseOptions(
  baseUrl: baseUrl,
  connectTimeout: const Duration(seconds: 10),
  receiveTimeout: const Duration(seconds: 30),
  contentType: Headers.jsonContentType,
  headers: {'Accept': 'application/json'},
);

/// The Dio every repository uses: JSON, timeouts and [AuthInterceptor].
///
/// [adapter] lets tests answer requests without a network.
Dio createApiClient({
  required String baseUrl,
  required TokenStore tokens,
  required void Function() onSessionExpired,
  HttpClientAdapter? adapter,
}) {
  final bare = Dio(_options(baseUrl));
  final dio = Dio(_options(baseUrl));
  if (adapter != null) {
    bare.httpClientAdapter = adapter;
    dio.httpClientAdapter = adapter;
  }
  dio.interceptors.add(
    AuthInterceptor(
      store: tokens,
      bareDio: bare,
      onSessionExpired: onSessionExpired,
    ),
  );
  return dio;
}
