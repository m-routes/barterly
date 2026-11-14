import 'package:barterly/src/api/token_store.dart';
import 'package:barterly/src/apply/application.dart';
import 'package:barterly/src/platform/device_keys.dart';
import 'package:barterly/src/platform/key_value_store.dart';
import 'package:flutter_test/flutter_test.dart';

import '../fixtures.dart';
import '../helpers.dart';

final String me = talentJson['id']! as String;

Map<String, Object?> savedDraft({String gigId = 'g1'}) => ApplicationDraft(
  localId: 'old-$gigId',
  gigId: gigId,
  gigTitle: 'Reception and social media volunteer',
  pitch: 'Written on the bus to Kasol.',
  proposedStart: gigStart,
  proposedEnd: gigStart.add(const Duration(days: 14)),
  createdAt: DateTime.utc(2026, 11, 13),
).toJson();

void main() {
  testWidgets('an application queued in an earlier session is sent at '
      'launch, from any tab', (tester) async {
    final store = MemoryKeyValueStore({
      DeviceKeys.outbox(me): {
        'drafts': [savedDraft()],
      },
    });
    final api = talentApi({
      'POST /api/v1/gigs/g1/applications/': (_) =>
          FakeResponse(201, applicationJson()),
    });
    usePhoneScreen(tester);
    await pumpApp(
      tester,
      api: api,
      tokens: MemoryTokenStore(signedInTokens),
      store: store,
    );
    // Still on Discover.
    expect(find.text('Gigs for you'), findsOneWidget);
    expect(api.calls, contains('POST /api/v1/gigs/g1/applications/'));
    expect(store.data[DeviceKeys.outbox(me)]?['drafts'], isEmpty);
  });

  testWidgets("another account's queued applications are left alone", (
    tester,
  ) async {
    final store = MemoryKeyValueStore({
      DeviceKeys.outbox('someone-else'): {
        'drafts': [savedDraft()],
      },
    });
    final api = talentApi();
    usePhoneScreen(tester);
    await pumpApp(
      tester,
      api: api,
      tokens: MemoryTokenStore(signedInTokens),
      store: store,
    );
    await tester.tap(find.text('My trips'));
    await tester.pumpAndSettle();
    expect(find.text('No trips yet'), findsOneWidget);
    expect(api.calls.where((c) => c.startsWith('POST')), isEmpty);
  });

  testWidgets('signing out forgets the offline feed and unsent applications', (
    tester,
  ) async {
    final store = MemoryKeyValueStore({
      DeviceKeys.outbox(me): {
        'drafts': [savedDraft()],
      },
    });
    final api = talentApi({
      // Can't send now: the draft stays queued.
      'POST /api/v1/gigs/g1/applications/': (_) => throw StateError('offline'),
      'GET /api/v1/gigs/': (_) => ok(page([gigJson()])),
      'POST /api/v1/auth/logout/': (_) => const FakeResponse(204),
    });
    usePhoneScreen(tester);
    await pumpApp(
      tester,
      api: api,
      tokens: MemoryTokenStore(signedInTokens),
      store: store,
    );
    expect(store.data.keys, contains(DeviceKeys.discoverCache(me)));
    expect(store.data[DeviceKeys.outbox(me)]?['drafts'], hasLength(1));

    await tester.tap(find.text('Profile'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Sign out'));
    await tester.tap(find.text('Sign out'));
    await tester.pumpAndSettle();

    expect(find.text('Sign in to Barterly'), findsOneWidget);
    expect(store.data.keys, isNot(contains(DeviceKeys.discoverCache(me))));
    expect(store.data.keys, isNot(contains(DeviceKeys.outbox(me))));
  });
}
