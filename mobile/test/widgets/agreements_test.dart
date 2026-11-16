import 'package:barterly/src/agreements/agreement_models.dart';
import 'package:barterly/src/agreements/offer_screen.dart';
import 'package:barterly/src/agreements/terms.dart';
import 'package:barterly/src/api/token_store.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

import '../fixtures.dart';
import '../helpers.dart';

const Map<String, Object?> termsJson = {
  'compensation_model': 'hybrid',
  'start_date': '2026-12-15',
  'end_date': '2027-01-10',
  'hours_per_day': 4,
  'days_per_week': 5,
  'stay_type': 'dorm_bed',
  'meals': 'two_meals',
  'stipend_amount': '5000.00',
  'stipend_period': 'per_month',
  'deliverables': [
    {'type': 'instagram_reel', 'quantity': 2, 'notes': ''},
  ],
  'usage_rights': {
    'scope': 'organic',
    'duration_months': 12,
    'credit_required': true,
  },
  'cancellation_policy': 'moderate',
};

Map<String, Object?> offerJson({
  String id = 'of1',
  String by = 'vendor',
  String status = 'open',
  Map<String, Object?> terms = termsJson,
  List<String> changed = const [],
  bool isFinal = false,
}) => {
  'id': id,
  'revision': by == 'vendor' ? 1 : 2,
  'proposed_by': by,
  'mine': by == 'talent',
  'terms': terms,
  'terms_sha256': 'a' * 64,
  'counter_of': null,
  'changed_fields': changed,
  'final': isFinal,
  'message': by == 'vendor' ? 'We would love to have you' : '',
  'status': status,
  'status_reason': '',
  'created_at': '2026-11-15T10:00:00Z',
  'answered_at': null,
};

Map<String, Object?> threadJson(
  List<Map<String, Object?>> offers, {
  String? open,
  bool yourTurn = false,
  bool canCounter = false,
}) => {
  'offers': offers,
  'open_offer': open,
  'your_turn': yourTurn,
  'can_counter': canCounter,
  'counterable': ['start_date', 'end_date', 'hours_per_day'],
  'offer_expires_at': '2026-11-17T10:00:00Z',
};

Map<String, Object?> agreementJson({bool signed = false}) => {
  'id': 'ag1',
  'booking': 'b1',
  'booking_status': 'confirmed',
  'gig_title': 'Reception and social media volunteer',
  'in_force': false,
  'current_version': null,
  'my_side': 'talent',
  'created_at': '2026-11-15T10:00:00Z',
  'versions': [
    {
      'id': 'v1',
      'number': 1,
      'status': 'awaiting',
      'status_reason': '',
      'terms': termsJson,
      'terms_sha256': 'b' * 64,
      'changed_fields': <String>[],
      'change_reason': '',
      'proposed_by': '',
      'template': 'agreement_v1',
      'template_reviewed': false,
      'pdf_ready': true,
      'pdf_sha256': 'c' * 64,
      'pdf_size': 17000,
      'signatures': [
        if (signed)
          {
            'party': 'talent',
            'signed_at': '2026-11-15T11:00:00Z',
            'provider': 'in_app_otp',
            'otp_confirmed': true,
            'document_sha256': 'c' * 64,
          },
      ],
      'signed_by_me': signed,
      'can_sign': !signed,
      'created_at': '2026-11-15T10:00:00Z',
      'in_force_at': null,
    },
  ],
};

/// The list on [screen], to scroll things on it into view.
Finder listOf(Type screen) => find
    .descendant(of: find.byType(screen), matching: find.byType(Scrollable))
    .first;

Future<void> openOffer(WidgetTester tester, FakeApi api) async {
  usePhoneScreen(tester);
  await pumpApp(tester, api: api, tokens: MemoryTokenStore(signedInTokens));
  await tester.tap(find.text('My trips'));
  await tester.pumpAndSettle();
  await tester.tap(find.text('See offer'));
  await tester.pumpAndSettle();
}

void main() {
  test('terms read as rows and mark what changed', () {
    final terms = Terms.fromJson(termsJson);
    final rows = {for (final (f, l, v) in terms.rows()) f: (l, v)};
    expect(rows['hours_per_day']!.$2, contains('at most 20 a week'));
    expect(rows['stipend_amount']!.$2, '₹5,000 per month');
    expect(rows['deliverables']!.$2, '2 × Instagram reel');
    expect(rows['usage_rights']!.$2, contains('12 months, with credit'));
    expect(rowChanged('hours_per_day', ['days_per_week']), isTrue);
    final thread = OfferThread.fromJson(
      threadJson([offerJson()], open: 'of1', yourTurn: true),
    );
    expect(thread.current!.id, 'of1');
  });

  testWidgets('asks for one change from My trips', (tester) async {
    var countered = false;
    final api = talentApi({
      'GET /api/v1/applications/mine/': (_) =>
          ok([applicationJson(status: 'offered')]),
      'GET /api/v1/applications/a1/offers/': (_) => ok(
        countered
            ? threadJson([
                offerJson(status: 'countered'),
                offerJson(
                  id: 'of2',
                  by: 'talent',
                  changed: ['hours_per_day'],
                  terms: {...termsJson, 'hours_per_day': 3},
                  isFinal: true,
                ),
              ], open: 'of2')
            : threadJson(
                [offerJson()],
                open: 'of1',
                yourTurn: true,
                canCounter: true,
              ),
      ),
      'POST /api/v1/offers/of1/counter/': (_) {
        countered = true;
        return FakeResponse(201, threadJson([offerJson()]));
      },
    });
    await openOffer(tester, api);

    expect(find.text('The host made you an offer'), findsOneWidget);
    expect(find.text('“We would love to have you”'), findsOneWidget);
    expect(find.text('₹5,000 per month'), findsOneWidget);

    await tester.scrollUntilVisible(
      find.text('Ask for a change'),
      200,
      scrollable: listOf(OfferScreen),
    );
    await tester.tap(find.text('Ask for a change'));
    await tester.pumpAndSettle();
    expect(
      tester
          .widget<FilledButton>(
            find.widgetWithText(FilledButton, 'Send my change'),
          )
          .onPressed,
      isNull,
      reason: 'nothing changed yet',
    );
    await tester.tap(find.byTooltip('Fewer hours a day'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextField, 'Message to the host (optional)'),
      'Three hours suits me',
    );
    await tester.tap(find.text('Send my change'));
    await tester.pumpAndSettle();

    final sent = api.requests.lastWhere((r) => r.path.endsWith('/counter/'));
    expect(sent.data, {
      'changes': {'hours_per_day': 3},
      'message': 'Three hours suits me',
    });
    await tester.drag(listOf(OfferScreen), const Offset(0, 2000));
    await tester.pumpAndSettle();
    expect(find.text('Your requested change'), findsOneWidget);
    expect(find.text('Changed'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.textContaining('The host will accept it'),
      200,
      scrollable: listOf(OfferScreen),
    );
    expect(find.textContaining('The host will accept it'), findsOneWidget);
  });

  testWidgets('accepts, then signs the agreement with a fresh OTP', (
    tester,
  ) async {
    var signed = false;
    final phone = FakePhoneAuth();
    final urls = FakeUrlOpener();
    final api = talentApi({
      'GET /api/v1/applications/mine/': (_) =>
          ok([applicationJson(status: 'offered')]),
      'GET /api/v1/applications/a1/offers/': (_) => ok(
        threadJson(
          [offerJson()],
          open: 'of1',
          yourTurn: true,
          canCounter: true,
        ),
      ),
      'POST /api/v1/offers/of1/accept/': (_) =>
          const FakeResponse(201, {'booking': 'b1', 'agreement_version': 'v1'}),
      'GET /api/v1/bookings/b1/agreement/': (_) => ok(agreementJson()),
      'GET /api/v1/agreements/ag1/': (_) => ok(agreementJson(signed: signed)),
      'GET /api/v1/agreement-versions/v1/pdf/': (_) => ok({
        'url': 'https://storage.test/v1.pdf',
        'expires_in': 600,
        'sha256': 'c' * 64,
        'size': 17000,
      }),
      'GET /api/v1/agreement-versions/v1/sign/': (_) => ok({
        'method': 'otp',
        'consent_text': 'I have read version 1 and I agree to its terms.',
        'phone_hint': '+91 ••••• 3210',
        'max_age_seconds': 300,
        'document_sha256': 'c' * 64,
      }),
      'POST /api/v1/agreement-versions/v1/sign/': (_) {
        signed = true;
        return ok(agreementJson(signed: true));
      },
    });
    usePhoneScreen(tester);
    await pumpApp(
      tester,
      api: api,
      tokens: MemoryTokenStore(signedInTokens),
      phoneAuth: phone,
      urls: urls,
    );
    await tester.tap(find.text('My trips'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('See offer'));
    await tester.pumpAndSettle();

    await tester.scrollUntilVisible(
      find.text('Accept and book'),
      200,
      scrollable: listOf(OfferScreen),
    );
    await tester.tap(find.text('Accept and book'));
    await tester.pumpAndSettle();
    expect(find.text('Agreement'), findsOneWidget);
    expect(find.textContaining('placeholder that a lawyer'), findsOneWidget);

    await tester.pump(const Duration(seconds: 5)); // the "booked" snackbar goes
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Open PDF'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Open PDF'));
    await tester.pumpAndSettle();
    expect(urls.inApp.single.toString(), 'https://storage.test/v1.pdf');

    await tester.ensureVisible(find.text('Sign version 1'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Sign version 1'));
    await tester.pumpAndSettle();
    await tester.tap(
      find.text('I have read version 1 and I agree to its terms.'),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Send a code to +91 ••••• 3210'));
    await tester.pumpAndSettle();
    expect(phone.sentTo, ['+919876543210']);
    await tester.enterText(find.byType(TextField), '123456');
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Sign'));
    await tester.pumpAndSettle();

    final sign = api.requests.lastWhere(
      (r) => r.method == 'POST' && r.path.endsWith('/sign/'),
    );
    expect(sign.data, {
      'consent': true,
      'document_sha256': 'c' * 64,
      'otp_token': 'firebase-id-token',
    });
    expect(sign.headers['X-Client-Device'], startsWith('Barterly app'));
    expect(phone.signedOut, isTrue);
    expect(find.textContaining('You: signed'), findsOneWidget);
    expect(find.text('Sign version 1'), findsNothing);
  });
}
