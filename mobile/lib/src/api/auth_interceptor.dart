import 'package:barterly/src/api/token_store.dart';
import 'package:dio/dio.dart';

/// Paths that carry no access token and never trigger a refresh.
const authPaths = {'/api/v1/auth/exchange/', '/api/v1/auth/refresh/'};

const _sentWithKey = 'barterly.sentWithAccess';
const _retriedKey = 'barterly.retried';

/// Adds `Authorization: Bearer` and refreshes the tokens on a 401.
///
/// Refresh tokens rotate and the old one is blacklisted, so two refreshes with
/// the same token would sign the person out. [QueuedInterceptor] handles errors
/// one at a time: the first 401 refreshes, and later ones see that the stored
/// access token changed since they were sent and just retry with it.
///
/// Retries and refreshes go through the bare Dio, which has no interceptors,
/// so a retried request can't re-enter this queue.
class AuthInterceptor extends QueuedInterceptor {
  new({
    required this._store,
    required this._bareDio,
    required this._onSessionExpired,
  });

  final TokenStore _store;
  final Dio _bareDio;
  final void Function() _onSessionExpired;

  bool _isAuthPath(RequestOptions options) => authPaths.contains(options.path);

  @override
  Future<void> onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    if (!_isAuthPath(options)) {
      final tokens = await _store.read();
      if (tokens != null) {
        options.headers['Authorization'] = 'Bearer ${tokens.access}';
        options.extra[_sentWithKey] = tokens.access;
      }
    }
    handler.next(options);
  }

  @override
  Future<void> onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    final options = err.requestOptions;
    if (err.response?.statusCode != 401 ||
        _isAuthPath(options) ||
        options.extra[_retriedKey] == true) {
      return handler.next(err);
    }

    final current = await _store.read();
    if (current == null) {
      _onSessionExpired();
      return handler.next(err);
    }

    var access = current.access;
    if (options.extra[_sentWithKey] == current.access) {
      // Nobody refreshed since this request went out: do it now.
      final refreshed = await _refresh(current.refresh);
      switch (refreshed) {
        case _Refreshed(:final tokens):
          access = tokens.access;
        case _Rejected():
          await _store.clear();
          _onSessionExpired();
          return handler.next(err);
        case _Failed():
          // Offline or the API is down: keep the session and report the error.
          return handler.next(err);
      }
    }

    try {
      options
        ..headers['Authorization'] = 'Bearer $access'
        ..extra[_retriedKey] = true;
      handler.resolve(await _bareDio.fetch<Object?>(options));
    } on DioException catch (retryError) {
      handler.next(retryError);
    }
  }

  Future<_RefreshResult> _refresh(String refresh) async {
    try {
      final response = await _bareDio.post<Map<String, Object?>>(
        '/api/v1/auth/refresh/',
        data: {'refresh': refresh},
      );
      final body = response.data;
      final access = body?['access'];
      final newRefresh = body?['refresh'];
      if (access is! String || newRefresh is! String) return const _Failed();
      final tokens = Tokens(access: access, refresh: newRefresh);
      await _store.write(tokens);
      return _Refreshed(tokens);
    } on DioException catch (error) {
      final status = error.response?.statusCode;
      // 401: expired or blacklisted. 400: malformed. Either way, it's over.
      if (status == 401 || status == 400) return const _Rejected();
      return const _Failed();
    }
  }
}

sealed class _RefreshResult {
  const new();
}

class _Refreshed extends _RefreshResult {
  const new(this.tokens);
  final Tokens tokens;
}

class _Rejected extends _RefreshResult {
  const new();
}

class _Failed extends _RefreshResult {
  const new();
}
