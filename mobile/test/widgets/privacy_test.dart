import 'package:barterly/src/api/token_store.dart';
import 'package:barterly/src/privacy/legal.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

import '../helpers.dart';

Map<String, Object?> consentJson(
  String purpose,
  String label, {
  bool granted = false,
  bool required = false,
}) => {
  'purpose': purpose,
  'label': label,
  'required': required,
  'granted': granted,
  'version': granted ? legalVersion : '',
  'current_version': legalVersion,
  'needs_renewal': false,
  'recorded_at': granted ? '2026-11-20T10:00:00Z' : null,
};

List<Map<String, Object?>> consents({bool location = true}) => [
  consentJson('terms', 'Terms of service', granted: true, required: true),
  consentJson('privacy', 'Privacy policy', granted: true, required: true),
  consentJson('location', 'Location use', granted: location),
  consentJson('social', 'Social account access'),
  consentJson('marketing', 'Marketing messages'),
];

const Map<String, Object?> noDeletion = {
  'request': null,
  'blockers': <Object?>[],
  'grace_days': 7,
};

Future<void> openPrivacy(
  WidgetTester tester,
  FakeApi api, {
  FakeUrlOpener? urls,
}) async {
  usePhoneScreen(tester);
  await pumpApp(
    tester,
    api: api,
    tokens: MemoryTokenStore(signedInTokens),
    urls: urls,
  );
  await tester.tap(find.text('Profile'));
  await tester.pumpAndSettle();
  await tester.scrollUntilVisible(
    find.text('Privacy and your data'),
    200,
    scrollable: find.byType(Scrollable).last,
  );
  await tester.tap(find.text('Privacy and your data'));
  await tester.pumpAndSettle();
}

/// Scrolls the privacy screen's list until [finder] is built and on screen.
Future<void> reveal(WidgetTester tester, Finder finder) async {
  await tester.scrollUntilVisible(
    finder,
    200,
    scrollable: find.byType(Scrollable).last,
  );
  await tester.ensureVisible(finder);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('withdrawing a consent is one switch, like giving it', (
    tester,
  ) async {
    var location = true;
    final posted = <Object?>[];
    final api = talentApi({
      'GET /api/v1/privacy/consents/': (_) => ok(consents(location: location)),
      'POST /api/v1/privacy/consents/': (r) {
        posted.add(r.data);
        location = (r.data as Map)['granted'] as bool;
        return ok(consents(location: location));
      },
      'GET /api/v1/privacy/deletion/': (_) => ok(noDeletion),
    });
    await openPrivacy(tester, api);

    final tile = find.widgetWithText(SwitchListTile, 'Location use');
    expect(tester.widget<SwitchListTile>(tile).value, isTrue);
    // The required consents have no switch.
    expect(
      find.widgetWithText(SwitchListTile, 'Terms of service'),
      findsNothing,
    );

    await tester.tap(tile);
    await tester.pumpAndSettle();
    expect(posted, [
      {'purpose': 'location', 'granted': false, 'source': 'mobile'},
    ]);
    expect(tester.widget<SwitchListTile>(tile).value, isFalse);
    expect(find.text('Location use: withdrawn.'), findsOneWidget);

    await tester.tap(tile);
    await tester.pumpAndSettle();
    expect(posted.last, {
      'purpose': 'location',
      'granted': true,
      'version': legalVersion,
      'source': 'mobile',
    });
  });

  testWidgets('downloads the data export through a short-lived link', (
    tester,
  ) async {
    final urls = FakeUrlOpener();
    final api = talentApi({
      'GET /api/v1/privacy/consents/': (_) => ok(consents()),
      'GET /api/v1/privacy/deletion/': (_) => ok(noDeletion),
      'POST /api/v1/privacy/exports/': (_) => const FakeResponse(201, {
        'id': 'e1',
        'status': 'ready',
        'size_bytes': 10,
        'created_at': '2026-11-21T10:00:00Z',
        'expires_at': '2026-11-22T10:00:00Z',
      }),
      'POST /api/v1/privacy/exports/e1/link/': (_) => ok({
        'url': 'https://storage.test/e1.json',
        'expires_in_seconds': 300,
      }),
    });
    await openPrivacy(tester, api, urls: urls);
    await reveal(tester, find.text('Download my data (JSON)'));
    await tester.tap(find.text('Download my data (JSON)'));
    await tester.pumpAndSettle();
    expect(urls.external, [Uri.parse('https://storage.test/e1.json')]);
  });

  testWidgets('deleting the account asks first, then can be undone', (
    tester,
  ) async {
    var scheduled = false;
    final api = talentApi({
      'GET /api/v1/privacy/consents/': (_) => ok(consents()),
      'GET /api/v1/privacy/deletion/': (_) => ok(
        scheduled
            ? {
                ...noDeletion,
                'request': {'scheduled_for': '2026-11-28T10:00:00Z'},
              }
            : noDeletion,
      ),
      'POST /api/v1/privacy/deletion/': (r) {
        expect(r.data, {'confirm': true});
        scheduled = true;
        return const FakeResponse(202, noDeletion);
      },
      'DELETE /api/v1/privacy/deletion/': (_) {
        scheduled = false;
        return ok({'status': 'cancelled'});
      },
    });
    await openPrivacy(tester, api);
    final delete = find.text('Delete my account');
    await reveal(tester, delete);
    await tester.tap(delete);
    await tester.pumpAndSettle();
    expect(find.text('Delete your account?'), findsOneWidget);
    await tester.tap(find.text('Delete'));
    await tester.pumpAndSettle();
    expect(find.textContaining('will be deleted on 28 Nov'), findsOneWidget);

    await tester.tap(find.text('Keep my account'));
    await tester.pumpAndSettle();
    expect(find.text('Delete my account'), findsOneWidget);
  });

  testWidgets('says what blocks deletion', (tester) async {
    final api = talentApi({
      'GET /api/v1/privacy/consents/': (_) => ok(consents()),
      'GET /api/v1/privacy/deletion/': (_) => ok({
        ...noDeletion,
        'blockers': [
          {
            'code': 'active_bookings',
            'count': 1,
            'message': 'Finish or cancel your bookings first.',
          },
        ],
      }),
    });
    await openPrivacy(tester, api);
    await reveal(tester, find.text('• Finish or cancel your bookings first.'));
    expect(find.text('Delete my account'), findsNothing);
  });

  testWidgets('changed terms are accepted again, each separately', (
    tester,
  ) async {
    var needsConsent = true;
    final posted = <Object?>[];
    final api = talentApi({
      'GET /api/v1/me/': (_) =>
          ok({...userJson(), 'needs_consent': needsConsent}),
      'POST /api/v1/privacy/consents/': (r) {
        posted.add(r.data);
        if (posted.length == 2) needsConsent = false;
        return ok(consents());
      },
    });
    usePhoneScreen(tester);
    await pumpApp(tester, api: api, tokens: MemoryTokenStore(signedInTokens));
    expect(find.text('Our terms have changed'), findsOneWidget);
    final accept = find.widgetWithText(FilledButton, 'Accept and continue');
    expect(tester.widget<FilledButton>(accept).onPressed, isNull);
    await tester.tap(find.text('I agree to the terms of service'));
    await tester.tap(find.text('I have read the privacy policy'));
    await tester.pump();
    await tester.tap(accept);
    await tester.pumpAndSettle();
    expect(posted, [
      {
        'purpose': 'terms',
        'granted': true,
        'version': legalVersion,
        'source': 'mobile',
      },
      {
        'purpose': 'privacy',
        'granted': true,
        'version': legalVersion,
        'source': 'mobile',
      },
    ]);
    expect(find.text('Our terms have changed'), findsNothing);
  });

  testWidgets('the legal pages open on the web site', (tester) async {
    final urls = FakeUrlOpener();
    final api = talentApi({
      'GET /api/v1/privacy/consents/': (_) => ok(consents()),
      'GET /api/v1/privacy/deletion/': (_) => ok(noDeletion),
    });
    await openPrivacy(tester, api, urls: urls);
    final grievance = find.text('Grievance Officer');
    await reveal(tester, grievance);
    await tester.tap(grievance);
    await tester.pump();
    expect(urls.inApp.single.path, '/grievance');
  });
}
