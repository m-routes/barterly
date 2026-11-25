import 'package:barterly/src/api/token_store.dart';
import 'package:barterly/src/auth/phone_auth.dart';
import 'package:barterly/src/privacy/legal.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

import '../helpers.dart';

Finder field(String label) => find.widgetWithText(TextFormField, label);

Future<void> enterPhone(WidgetTester tester, String phone) async {
  await tester.enterText(field('Mobile number'), phone);
  await tester.tap(find.text('Send code'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('signed-out launch shows sign-in', (tester) async {
    await pumpApp(tester, api: FakeApi());
    expect(find.text('Sign in to Barterly'), findsOneWidget);
  });

  testWidgets('checks the number before sending a code', (tester) async {
    final auth = FakePhoneAuth();
    await pumpApp(tester, api: FakeApi(), phoneAuth: auth);
    await enterPhone(tester, '12345');
    expect(find.text('Enter a 10-digit Indian mobile number.'), findsOneWidget);
    expect(auth.sentTo, isEmpty);
  });

  testWidgets('explains Firebase errors', (tester) async {
    final auth = FakePhoneAuth(
      sendError: PhoneAuthException.fromCode('too-many-requests'),
    );
    await pumpApp(tester, api: FakeApi(), phoneAuth: auth);
    await enterPhone(tester, '98765 43210');
    expect(find.textContaining('Too many attempts'), findsOneWidget);
  });

  testWidgets('a wrong code stays on the code step', (tester) async {
    final api = FakeApi();
    await pumpApp(tester, api: api, phoneAuth: FakePhoneAuth());
    await enterPhone(tester, '98765 43210');
    expect(find.text('Enter your code'), findsOneWidget);
    expect(find.textContaining('+919876543210'), findsOneWidget);

    await tester.enterText(field('Code'), '000000');
    await tester.tap(find.text('Verify and continue'));
    await tester.pumpAndSettle();
    expect(find.textContaining("That code isn't right"), findsOneWidget);
    expect(api.requests, isEmpty);
  });

  testWidgets('the right code signs in, stores tokens and moves on', (
    tester,
  ) async {
    final tokens = MemoryTokenStore();
    final auth = FakePhoneAuth();
    final api = FakeApi({
      'POST /api/v1/auth/exchange/': (_) => ok({
        'access': 'a',
        'refresh': 'r',
        'is_new_user': true,
        'needs_role': true,
        'profile_complete': false,
        'user': userJson(role: '', complete: false),
      }),
    });
    await pumpApp(tester, api: api, tokens: tokens, phoneAuth: auth);
    await enterPhone(tester, '9876543210');
    await tester.enterText(field('Code'), '123456');
    await tester.tap(find.text('Verify and continue'));
    await tester.pumpAndSettle();

    expect((await tokens.read())?.access, 'a');
    expect(auth.signedOut, isTrue, reason: 'Firebase session is dropped');
    // New account: the router asks them to join as talent.
    expect(find.text('Join as talent'), findsWidgets);
  });

  testWidgets('shows the API message when the exchange fails', (tester) async {
    final api = FakeApi({
      'POST /api/v1/auth/exchange/': (_) =>
          apiError(403, 'account_disabled', 'This account has been disabled.'),
    });
    await pumpApp(tester, api: api, phoneAuth: FakePhoneAuth());
    await enterPhone(tester, '9876543210');
    await tester.enterText(field('Code'), '123456');
    await tester.tap(find.text('Verify and continue'));
    await tester.pumpAndSettle();
    expect(find.text('This account has been disabled.'), findsOneWidget);
  });

  testWidgets('joining as talent sets the role and opens setup', (
    tester,
  ) async {
    var role = '';
    final api = FakeApi({
      'GET /api/v1/me/': (_) => ok(userJson(role: role, complete: false)),
      'POST /api/v1/me/role/': (r) {
        expect(r.data, {
          'role': 'talent',
          'confirm_adult': true,
          'terms_version': legalVersion,
          'privacy_version': legalVersion,
          'source': 'mobile',
        });
        role = 'talent';
        return ok(userJson(complete: false));
      },
      'GET /api/v1/profiles/talent/me/': (_) =>
          apiError(404, 'profile_not_found'),
      'GET /api/v1/profiles/skills/': (_) => ok(skillsJson),
    });
    usePhoneScreen(tester);
    await pumpApp(tester, api: api, tokens: MemoryTokenStore(signedInTokens));
    final join = find.widgetWithText(FilledButton, 'Join as talent');
    // Nothing is pre-ticked: 18+, the terms and the privacy policy, each.
    expect(tester.widget<FilledButton>(join).onPressed, isNull);
    await tester.tap(find.text('I am 18 or older'));
    await tester.tap(find.text('I agree to the terms of service'));
    await tester.pump();
    expect(tester.widget<FilledButton>(join).onPressed, isNull);
    await tester.tap(find.text('I have read the privacy policy'));
    await tester.pump();
    await tester.ensureVisible(join);
    await tester.tap(join);
    await tester.pumpAndSettle();
    expect(find.text('Set up your profile'), findsOneWidget);
  });

  testWidgets('during the closed beta, joining asks for the invite code', (
    tester,
  ) async {
    var role = '';
    final sent = <Object?>[];
    final api = FakeApi({
      'GET /api/v1/me/': (_) => ok(userJson(role: role, complete: false)),
      'GET /api/v1/beta/': (_) => ok({
        'closed_beta': true,
        'invite_required_for': ['vendor', 'talent'],
        'max_live_gigs': 2,
        'max_stipend_rupees': 20000,
      }),
      'POST /api/v1/me/role/': (r) {
        sent.add(r.data);
        final code = (r.data as Map)['invite_code'];
        if (code != 'ABCD-2345') {
          return apiError(400, 'invite_invalid', "That code isn't right.");
        }
        role = 'talent';
        return ok(userJson(complete: false));
      },
      'GET /api/v1/profiles/talent/me/': (_) =>
          apiError(404, 'profile_not_found'),
      'GET /api/v1/profiles/skills/': (_) => ok(skillsJson),
    });
    usePhoneScreen(tester);
    await pumpApp(tester, api: api, tokens: MemoryTokenStore(signedInTokens));
    Future<void> tapIn(Finder finder) async {
      await tester.scrollUntilVisible(
        finder,
        100,
        scrollable: find.byType(Scrollable).last,
      );
      await tester.tap(finder);
      await tester.pumpAndSettle();
    }

    final invite = find.widgetWithText(TextField, 'Invite code');
    expect(
      invite,
      findsOneWidget,
      reason: 'the beta rules say talent need one',
    );
    await tapIn(find.text('I am 18 or older'));
    await tapIn(find.text('I agree to the terms of service'));
    await tapIn(find.text('I have read the privacy policy'));
    final join = find.widgetWithText(FilledButton, 'Join as talent');
    await tapIn(join);
    expect(find.text('Enter the invite code we sent you.'), findsOneWidget);
    expect(sent, isEmpty);

    await tester.enterText(invite, 'WRONG-CODE');
    await tapIn(join);
    expect(find.text("That code isn't right."), findsOneWidget);

    await tester.enterText(invite, 'ABCD-2345');
    await tapIn(join);
    expect(find.text('Set up your profile'), findsOneWidget);
  });

  testWidgets('vendors are pointed at the web console', (tester) async {
    final api = FakeApi({
      'GET /api/v1/me/': (_) => ok(userJson(role: 'vendor')),
    });
    await pumpApp(tester, api: api, tokens: MemoryTokenStore(signedInTokens));
    expect(find.text('This app is for talent'), findsOneWidget);
  });
}
