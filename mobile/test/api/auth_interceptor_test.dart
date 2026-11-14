import 'dart:async';

import 'package:barterly/src/api/api_client.dart';
import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/api/token_store.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers.dart';

void main() {
  late FakeApi api;
  late MemoryTokenStore tokens;
  late int expired;
  late Dio dio;

  setUp(() {
    api = FakeApi();
    tokens = MemoryTokenStore(signedInTokens);
    expired = 0;
    dio = createApiClient(
      baseUrl: 'http://api.test',
      tokens: tokens,
      adapter: api,
      onSessionExpired: () => expired++,
    );
  });

  String? bearer(RequestOptions r) => r.headers['Authorization'] as String?;

  /// 401 for requests sent with the first access token, [body] after.
  Handler staleThen(Object body) =>
      (r) => bearer(r) == 'Bearer access-1'
      ? apiError(401, 'token_not_valid')
      : ok(body);

  test('sends the access token', () async {
    api.routes['GET /api/v1/me/'] = (_) => ok(talentJson);
    await dio.get<Object?>('/api/v1/me/');
    expect(bearer(api.requests.single), 'Bearer access-1');
  });

  test('refreshes once on a 401, stores the new tokens and retries', () async {
    api.routes['GET /api/v1/me/'] = staleThen(talentJson);
    api.routes['POST /api/v1/auth/refresh/'] = (r) {
      expect(r.data, {'refresh': 'refresh-1'});
      expect(bearer(r), isNull, reason: 'refresh carries no access token');
      return ok({'access': 'access-2', 'refresh': 'refresh-2'});
    };

    final response = await dio.get<Object?>('/api/v1/me/');

    expect(response.statusCode, 200);
    expect(api.calls, [
      'GET /api/v1/me/',
      'POST /api/v1/auth/refresh/',
      'GET /api/v1/me/',
    ]);
    expect(bearer(api.requests.last), 'Bearer access-2');
    final stored = await tokens.read();
    expect((stored!.access, stored.refresh), ('access-2', 'refresh-2'));
  });

  test('parallel 401s share one refresh (refresh tokens rotate)', () async {
    var refreshes = 0;
    final gate = Completer<void>();
    api.routes['GET /api/v1/me/'] = staleThen(talentJson);
    api.routes['GET /api/v1/profiles/skills/'] = staleThen(skillsJson);
    api.routes['POST /api/v1/auth/refresh/'] = (_) async {
      refreshes++;
      await gate.future;
      return ok({'access': 'access-2', 'refresh': 'refresh-2'});
    };

    final both = Future.wait([
      dio.get<Object?>('/api/v1/me/'),
      dio.get<Object?>('/api/v1/profiles/skills/'),
    ]);
    await Future<void>.delayed(const Duration(milliseconds: 10));
    gate.complete();
    final results = await both;

    expect(results.map((r) => r.statusCode), [200, 200]);
    expect(refreshes, 1);
  });

  test('a rejected refresh clears the tokens and reports expiry', () async {
    api.routes['GET /api/v1/me/'] = (_) => apiError(401, 'token_not_valid');
    api.routes['POST /api/v1/auth/refresh/'] = (_) =>
        apiError(401, 'token_not_valid');

    final error = await guardApi(() => dio.get<Object?>('/api/v1/me/'))
        .then<Object?>((_) => null, onError: (Object e) => e);

    expect(error, isA<ApiError>().having((e) => e.status, 'status', 401));
    expect(await tokens.read(), isNull);
    expect(expired, 1);
  });

  test('a refresh that fails for other reasons keeps the session', () async {
    api.routes['GET /api/v1/me/'] = (_) => apiError(401, 'token_not_valid');
    api.routes['POST /api/v1/auth/refresh/'] = (_) =>
        apiError(503, 'unavailable');

    await expectLater(
      dio.get<Object?>('/api/v1/me/'),
      throwsA(isA<DioException>()),
    );
    expect(await tokens.read(), isNotNull);
    expect(expired, 0);
  });

  test('a 401 with no stored tokens reports expiry, no refresh', () async {
    await tokens.clear();
    api.routes['GET /api/v1/me/'] = (_) => apiError(401, 'not_authenticated');

    await expectLater(
      dio.get<Object?>('/api/v1/me/'),
      throwsA(isA<DioException>()),
    );
    expect(api.calls, ['GET /api/v1/me/']);
    expect(expired, 1);
  });

  test('auth endpoints never trigger a refresh', () async {
    api.routes['POST /api/v1/auth/exchange/'] = (_) =>
        apiError(401, 'invalid_sign_in_token');
    await expectLater(
      dio.post<Object?>('/api/v1/auth/exchange/', data: {'id_token': 'x'}),
      throwsA(isA<DioException>()),
    );
    expect(api.calls, ['POST /api/v1/auth/exchange/']);
    expect(bearer(api.requests.single), isNull);
  });

  test('API errors keep their code, details and request id', () async {
    api.routes['PATCH /api/v1/profiles/talent/me/'] = (_) => const FakeResponse(
      400,
      {
        'code': 'validation_error',
        'message': 'Invalid input.',
        'details': {
          'date_of_birth': ['You must be at least 18 to join Barterly.'],
          'non_field_errors': ['Nope.'],
        },
      },
      {'x-request-id': 'req-1'},
    );
    final error = await guardApi(
      () => dio.patch<Object?>('/api/v1/profiles/talent/me/', data: {}),
    ).then<Object?>((_) => null, onError: (Object e) => e);

    expect(error, isA<ApiError>());
    final apiErr = error! as ApiError;
    expect(apiErr.requestId, 'req-1');
    expect(apiErr.fieldErrors, {
      'date_of_birth': 'You must be at least 18 to join Barterly.',
      'root': 'Nope.',
    });
  });

  test('no response at all is a network_error', () {
    final error = ApiError.fromDio(
      DioException.connectionError(
        requestOptions: RequestOptions(path: '/x'),
        reason: 'offline',
      ),
    );
    expect((error.status, error.code), (0, 'network_error'));
  });
}
