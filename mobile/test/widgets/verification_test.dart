import 'package:barterly/src/api/token_store.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

import '../helpers.dart';

Map<String, Object?> caseJson(
  String status, {
  Map<String, Object?> details = const {},
  String reason = '',
}) => {
  'id': 'c-$status',
  'check_type': 'id_selfie',
  'subject_type': 'user',
  'property_id': null,
  'status': status,
  'reason': reason,
  'details': details,
  'submitted_at': null,
  'reviewed_at': null,
  'approved_at': null,
  'expires_at': null,
  'documents': <Object?>[],
};

Map<String, Object?> meJson({
  List<Map<String, Object?>> idCases = const [],
  List<Map<String, Object?>> socialCases = const [],
  List<String> badges = const [],
}) => {
  'checks': [
    {
      'check_type': 'id_selfie',
      'label': 'Government ID and selfie',
      'required': true,
      'badge': 'id_verified',
      'cases': idCases,
    },
    {
      'check_type': 'social_account',
      'label': 'Linked social account',
      'required': true,
      'badge': 'social_verified',
      'cases': socialCases,
    },
    {
      'check_type': 'reference',
      'label': 'Reference',
      'required': false,
      'badge': 'reference_checked',
      'cases': <Object?>[],
    },
  ],
  'badges': [
    for (final b in badges)
      {
        'kind': b,
        'granted_at': '2026-11-01T10:00:00Z',
        'grant_reason': '',
        'case_id': null,
      },
  ],
  'trusted_member': badges.contains('trusted_member'),
};

Future<void> openVerification(
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
  await tester.tap(find.text('Verification and badges'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('shows each check with its status and no badges yet', (
    tester,
  ) async {
    await openVerification(
      tester,
      talentApi({'GET /api/v1/verification/me/': (_) => ok(meJson())}),
    );
    expect(find.text('Government ID and selfie'), findsOneWidget);
    expect(find.text('Linked social account'), findsOneWidget);
    // Two cards fit on screen; the optional reference check is below.
    expect(find.text('Not started'), findsNWidgets(2));
    expect(
      find.text('No badges yet. Each check you pass adds one.'),
      findsOneWidget,
    );
    expect(find.text('Verify my ID'), findsOneWidget);
    expect(find.text('Link Instagram'), findsOneWidget);
  });

  testWidgets('earned badges and pending checks', (tester) async {
    await openVerification(
      tester,
      talentApi({
        'GET /api/v1/verification/me/': (_) => ok(
          meJson(
            idCases: [caseJson('approved')],
            socialCases: [
              caseJson('submitted', details: {'bio_code': 'BARTERLY-1A2B3C'}),
            ],
            badges: ['id_verified', 'trusted_member'],
          ),
        ),
      }),
    );
    expect(find.text('ID verified'), findsOneWidget);
    expect(find.text('Trusted member'), findsOneWidget);
    expect(find.textContaining("You're a trusted member"), findsOneWidget);
    expect(find.text('Verified'), findsOneWidget);
    expect(find.text('Submitted'), findsOneWidget);
    expect(find.text('BARTERLY-1A2B3C'), findsOneWidget);
    expect(find.text('Verify my ID'), findsNothing);
  });

  testWidgets('a rejected ID check shows why and offers another try', (
    tester,
  ) async {
    await openVerification(
      tester,
      talentApi({
        'GET /api/v1/verification/me/': (_) => ok(
          meJson(
            idCases: [caseJson('rejected', reason: 'The photo was blurry.')],
          ),
        ),
      }),
    );
    expect(find.text('Not approved'), findsOneWidget);
    expect(find.text('The photo was blurry.'), findsOneWidget);
    expect(find.text('Try again'), findsOneWidget);
  });

  testWidgets("the ID check opens the provider's page in the in-app browser", (
    tester,
  ) async {
    final urls = FakeUrlOpener();
    final api = talentApi({
      'GET /api/v1/verification/me/': (_) => ok(meJson()),
      'POST /api/v1/verification/checks/id/': (_) => ok({
        'case': caseJson('submitted'),
        'session': {
          'reference': 'ref-1',
          'client_token': 'tok',
          'redirect_url': 'https://kyc.example.com/s/ref-1',
          'expires_in_seconds': 900,
        },
      }),
    });
    await openVerification(tester, api, urls: urls);
    await tester.tap(find.text('Verify my ID'));
    await tester.pumpAndSettle();
    expect(find.text('Which ID will you use?'), findsOneWidget);
    await tester.tap(find.text('Aadhaar'));
    await tester.pumpAndSettle();

    final start = api.requests.firstWhere((r) => r.method == 'POST');
    expect(start.data, {'document_type': 'aadhaar'});
    expect(urls.inApp, [Uri.parse('https://kyc.example.com/s/ref-1')]);
    expect(urls.external, isEmpty);
  });

  testWidgets("a non-https provider page isn't opened", (tester) async {
    final urls = FakeUrlOpener();
    final api = talentApi({
      'GET /api/v1/verification/me/': (_) => ok(meJson()),
      'POST /api/v1/verification/checks/id/': (_) => ok({
        'case': caseJson('submitted'),
        'session': {
          'reference': 'ref-1',
          'client_token': '',
          'redirect_url': 'http://kyc.example.com/s/ref-1',
          'expires_in_seconds': 900,
        },
      }),
    });
    await openVerification(tester, api, urls: urls);
    await tester.tap(find.text('Verify my ID'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Passport'));
    await tester.pumpAndSettle();
    expect(urls.inApp, isEmpty);
    expect(
      find.text("ID verification isn't available right now. Try again later."),
      findsOneWidget,
    );
  });

  testWidgets('no KYC provider configured (503) is explained', (tester) async {
    final urls = FakeUrlOpener();
    await openVerification(
      tester,
      talentApi({
        'GET /api/v1/verification/me/': (_) => ok(meJson()),
        'POST /api/v1/verification/checks/id/': (_) => apiError(
          503,
          'kyc_unavailable',
          "ID verification isn't available right now. Try again later.",
        ),
      }),
      urls: urls,
    );
    await tester.tap(find.text('Verify my ID'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Voter ID'));
    await tester.pumpAndSettle();
    expect(urls.inApp, isEmpty);
    expect(find.textContaining("isn't available right now"), findsOneWidget);
  });

  testWidgets('linking Instagram saves the handle and shows the bio code', (
    tester,
  ) async {
    var submitted = false;
    final api = talentApi({
      'GET /api/v1/verification/me/': (_) => ok(
        meJson(
          socialCases: [
            if (submitted)
              caseJson('submitted', details: {'bio_code': 'BARTERLY-9F8E7D'}),
          ],
        ),
      ),
      'PATCH /api/v1/profiles/talent/me/': (r) =>
          ok({...r.data! as Map<String, Object?>, 'profile_complete': true}),
      'POST /api/v1/verification/checks/social/': (_) {
        submitted = true;
        return ok(
          caseJson('submitted', details: {'bio_code': 'BARTERLY-9F8E7D'}),
        );
      },
    });
    await openVerification(tester, api);
    await tester.ensureVisible(find.text('Link Instagram'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Link Instagram'));
    await tester.pumpAndSettle();

    final field = find.widgetWithText(TextFormField, 'Instagram username');
    expect(
      tester.widget<TextFormField>(field).controller?.text,
      'asha.paints',
      reason: 'prefilled from the profile',
    );
    await tester.enterText(field, 'not valid!');
    await tester.tap(find.text('Submit for checking'));
    await tester.pumpAndSettle();
    expect(
      find.text('Use letters, numbers, dots and underscores only.'),
      findsOneWidget,
    );

    await tester.enterText(field, '@asha.murals');
    await tester.tap(find.text('Submit for checking'));
    await tester.pumpAndSettle();

    final patch = api.requests.firstWhere((r) => r.method == 'PATCH');
    expect(patch.data, {'instagram_handle': 'asha.murals'});
    expect(api.calls, contains('POST /api/v1/verification/checks/social/'));
    expect(find.text('BARTERLY-9F8E7D'), findsWidgets);

    await tester.tap(find.text('Done'));
    await tester.pumpAndSettle();
    expect(find.text('Submitted'), findsOneWidget);
  });

  testWidgets('a failed load offers a retry', (tester) async {
    final api = talentApi({
      'GET /api/v1/verification/me/': (_) =>
          apiError(500, 'server_error', 'Down.'),
    });
    await openVerification(tester, api);
    expect(find.text("We couldn't load your verification"), findsOneWidget);
    api.routes['GET /api/v1/verification/me/'] = (_) => ok(meJson());
    await tester.tap(find.text('Try again'));
    await tester.pumpAndSettle();
    expect(find.text('Government ID and selfie'), findsOneWidget);
  });
}
