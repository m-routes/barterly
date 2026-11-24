import 'package:barterly/src/api/api_client.dart';
import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/api/token_store.dart';
import 'package:barterly/src/update/app_version.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers.dart';

void main() {
  group('AppVersion', () {
    test('parses like the server and ignores build and pre-release', () {
      expect(AppVersion.parse('1.4.2'), const AppVersion(1, 4, 2));
      expect(AppVersion.parse(' 1.4.2+17 '), const AppVersion(1, 4, 2));
      expect(AppVersion.parse('2.0.0-rc1'), const AppVersion(2, 0, 0));
      for (final bad in ['1.4', '', 'v1.2.3', null]) {
        expect(AppVersion.parse(bad), isNull, reason: '$bad');
      }
    });

    test('compares numerically, not as text', () {
      expect(const AppVersion(1, 10, 0) < const AppVersion(1, 9, 9), isFalse);
      expect(const AppVersion(1, 9, 9) < const AppVersion(1, 10, 0), isTrue);
      expect(const AppVersion(2, 0, 0).compareTo(const AppVersion(2, 0, 0)), 0);
    });
  });

  test('needFor: required, available, none; unreadable is never blocked', () {
    const policy = UpdatePolicy(
      minimumVersion: '1.2.0',
      latestVersion: '1.4.0',
    );
    expect(policy.needFor('1.1.9'), UpdateNeed.required);
    expect(policy.needFor('1.2.0'), UpdateNeed.available);
    expect(policy.needFor('1.4.0+99'), UpdateNeed.none);
    expect(policy.needFor('garbage'), UpdateNeed.none);
  });

  group('ClientVersionInterceptor', () {
    late FakeApi api;
    late List<UpdatePolicy> required;

    setUp(() => required = []);

    ApiErrorTestClient client({InstalledApp install = testInstall}) {
      api = FakeApi();
      final dio = createApiClient(
        baseUrl: 'http://api.test',
        tokens: MemoryTokenStore(signedInTokens),
        adapter: api,
        onSessionExpired: () {},
        interceptors: [
          ClientVersionInterceptor(
            installed: () async => install,
            onUpgradeRequired: required.add,
          ),
        ],
      );
      return ApiErrorTestClient(dio);
    }

    test('sends the platform and version on every call', () async {
      final c = client();
      api.routes['GET /api/v1/me/'] = (_) => ok(talentJson);
      await c.get('/api/v1/me/');
      final headers = api.requests.single.headers;
      expect(headers['X-Client-Platform'], 'android');
      expect(headers['X-Client-Version'], '1.0.0');
    });

    test('sends nothing where the platform is unknown', () async {
      final c = client(
        install: const InstalledApp(
          version: '1.0.0',
          buildNumber: '1',
          platform: '',
        ),
      );
      api.routes['GET /api/v1/me/'] = (_) => ok(talentJson);
      await c.get('/api/v1/me/');
      expect(api.requests.single.headers['X-Client-Version'], isNull);
    });

    test('a 426 upgrade_required reports the policy and still fails', () async {
      final c = client();
      api.routes['GET /api/v1/me/'] = (_) => apiError(
        426,
        'upgrade_required',
        'Update for the new payouts.',
        {'minimum_version': '1.2.0', 'store_url': 'https://store.test/app'},
      );
      await expectLater(
        c.get('/api/v1/me/'),
        throwsA(isA<ApiError>().having((e) => e.status, 'status', 426)),
      );
      expect(required.single.minimumVersion, '1.2.0');
      expect(required.single.storeUrl, 'https://store.test/app');
      expect(required.single.message, 'Update for the new payouts.');
    });

    test('other errors are not upgrades', () async {
      final c = client();
      api.routes['GET /api/v1/me/'] = (_) => apiError(400, 'validation_error');
      await expectLater(c.get('/api/v1/me/'), throwsA(isA<ApiError>()));
      expect(required, isEmpty);
    });
  });
}

/// guardApi around a Dio, for the interceptor tests.
class ApiErrorTestClient {
  const new(this._dio);

  final Dio _dio;

  Future<Object?> get(String path) =>
      guardApi(() async => (await _dio.get<Object?>(path)).data);
}
