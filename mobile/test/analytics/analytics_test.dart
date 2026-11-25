import 'package:barterly/src/analytics/analytics.dart';
import 'package:barterly/src/analytics/events.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers.dart';

Dio dioFor(FakeApi api) =>
    Dio(BaseOptions(baseUrl: 'https://api.test'))..httpClientAdapter = api;

List<Object?> consents({required bool analytics}) => [
  {'purpose': 'terms', 'granted': true},
  {'purpose': 'analytics', 'granted': analytics},
];

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('screen names drop ids', () {
    expect(
      screenOf('/trips/agreement/3f2a6c1e-8b7d-4e0f-9a1b-2c3d4e5f6a7b'),
      'trips/agreement',
    );
    expect(screenOf('/'), 'home');
  });

  test('nothing is sent without consent', () async {
    final api = FakeApi({
      'GET /api/v1/privacy/consents/': (_) => ok(consents(analytics: false)),
    });
    final analytics = Analytics(dioFor(api), batchSize: 1)
      ..track('help_opened', {'screen': 'profile'});
    await analytics.flush();
    expect(api.calls, ['GET /api/v1/privacy/consents/']);
    expect(analytics.consent, isFalse);
    analytics.track('help_opened', {'screen': 'profile'});
    await analytics.flush();
    expect(api.calls, hasLength(1), reason: 'no more checks once it is no');
  });

  test('with consent, events go in batches', () async {
    Object? sent;
    final api = FakeApi({
      'GET /api/v1/privacy/consents/': (_) => ok(consents(analytics: true)),
      'POST /api/v1/analytics/events/': (r) {
        sent = r.data;
        return ok({'accepted': 2, 'dropped': 0, 'consent': true});
      },
    });
    final analytics = Analytics(dioFor(api), batchSize: 2)
      ..track('screen_view', {'screen': 'discover'});
    expect(api.calls, isEmpty, reason: 'waits for a full batch');
    analytics.track('apply_started', {'gig_id': 'g1'});
    await analytics.flush();
    final events = (sent! as Map)['events'] as List;
    expect(
      [for (final e in events) (e as Map)['name']],
      ['screen_view', 'apply_started'],
    );
  });

  test('withdrawing drops what was waiting', () async {
    final api = FakeApi();
    final analytics = Analytics(dioFor(api))
      ..setConsent(granted: true)
      ..track('search', {'filters': 1, 'results': 3})
      ..setConsent(granted: false);
    expect(analytics.queued, 0);
    await analytics.flush();
    expect(api.calls, isEmpty);
  });
}
