import 'dart:convert';

import 'package:barterly/src/api/token_store.dart';
import 'package:barterly/src/app.dart';
import 'package:barterly/src/auth/phone_auth.dart';
import 'package:barterly/src/config/env.dart';
import 'package:barterly/src/notifications/push.dart';
import 'package:barterly/src/platform/network_status.dart';
import 'package:barterly/src/providers.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

/// The talent-side acceptance journeys run the real app against a real API
/// (docs/qa/README.md):
///
/// - the local acceptance stack: phone sign-in is a local fake (code 123456),
///   the API's fake verifier accepts its tokens;
/// - staging: Firebase phone sign-in with the persona's test number.
///
/// Everything comes in with --dart-define (see mobile/tool/acceptance.sh).
abstract final class Acceptance {
  static const apiUrl = String.fromEnvironment('ACCEPTANCE_API_URL');
  static const local = bool.fromEnvironment('ACCEPTANCE_LOCAL');
  static const phone = String.fromEnvironment('ACCEPTANCE_TALENT_PHONE');
  static const code = String.fromEnvironment(
    'ACCEPTANCE_OTP_CODE',
    defaultValue: '123456',
  );
  static const _fixtures = String.fromEnvironment('ACCEPTANCE_FIXTURES');

  static bool get configured => apiUrl.isNotEmpty && phone.isNotEmpty;

  /// What `manage.py prepare_journey` printed for this talent (base64 JSON).
  static Map<String, Object?> get fixtures => _fixtures.isEmpty
      ? const {}
      : jsonDecode(utf8.decode(base64.decode(_fixtures)))
            as Map<String, Object?>;

  static String fixture(String key) {
    final value = fixtures[key];
    if (value is! String) throw StateError('No $key in ACCEPTANCE_FIXTURES');
    return value;
  }

  /// The person types it without the +91.
  static String get national => phone.replaceFirst('+91', '');
}

/// The local stack's phone sign-in: no Firebase, tokens the API's local fake
/// verifier accepts.
class LocalFakePhoneAuth implements PhoneAuth {
  @override
  Future<PhoneVerification> sendCode(String phoneE164) async =>
      CodeSent((code) async {
        if (code != Acceptance.code) {
          throw PhoneAuthException.fromCode('invalid-verification-code');
        }
        final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
        return 'fake-otp:$phoneE164@$now';
      });

  @override
  Future<void> signOut() async {}
}

Future<PhoneAuth> _phoneAuth(AppConfig config) async {
  if (Acceptance.local) return LocalFakePhoneAuth();
  final firebase = config.firebase;
  if (firebase == null) throw StateError('Staging runs need Firebase config');
  await Firebase.initializeApp(options: firebase);
  // Only Firebase test numbers work with this on; the suite only uses those.
  await FirebaseAuth.instance.setSettings(
    appVerificationDisabledForTesting: true,
  );
  return FirebasePhoneAuth();
}

/// The app, fresh (signed out), talking to the acceptance API. Pass [network]
/// to control what the app believes about connectivity.
Future<void> launchApp(WidgetTester tester, {NetworkStatus? network}) async {
  final base = AppConfig.fromEnvironment();
  final config = AppConfig(
    env: base.env,
    apiBaseUrl: Acceptance.apiUrl,
    firebase: base.firebase,
  );
  final phoneAuth = await _phoneAuth(config);
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        appConfigProvider.overrideWithValue(config),
        tokenStoreProvider.overrideWithValue(MemoryTokenStore()),
        phoneAuthProvider.overrideWithValue(phoneAuth),
        pushMessagingProvider.overrideWithValue(const NoPushMessaging()),
        if (network != null) networkStatusProvider.overrideWithValue(network),
      ],
      child: const BarterlyApp(brandFonts: false),
    ),
  );
  await settle(tester);
}

/// Pumps frames for a while: real network calls and spinners never "settle".
Future<void> settle(WidgetTester tester, {int seconds = 2}) async {
  for (var i = 0; i < seconds * 10; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

/// Waits until [finder] finds something, pumping frames (network-backed UI).
Future<void> waitFor(
  WidgetTester tester,
  Finder finder, {
  Duration timeout = const Duration(seconds: 30),
}) async {
  final end = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(end)) {
    await tester.pump(const Duration(milliseconds: 250));
    if (finder.evaluate().isNotEmpty) return;
  }
  final onScreen = [
    for (final e in find.byType(Text).evaluate())
      if ((e.widget as Text).data case final String text) text,
  ];
  throw TestFailure('Timed out waiting for $finder.\nOn screen: $onScreen');
}

Future<void> signIn(WidgetTester tester) async {
  await waitFor(tester, find.text('Sign in to Barterly'));
  await tester.enterText(
    find.widgetWithText(TextField, 'Mobile number'),
    Acceptance.national,
  );
  await tester.tap(find.text('Send code'));
  await waitFor(tester, find.text('Enter your code'));
  await tester.enterText(
    find.widgetWithText(TextField, 'Code'),
    Acceptance.code,
  );
  await tester.tap(find.text('Verify and continue'));
  await waitFor(tester, find.text('Discover'));
}

/// Opens a screen by its route, as a notification or deep link would.
void go(WidgetTester tester, String location) {
  final context = tester.element(find.byType(Scaffold).first);
  clearSnackBars(tester);
  GoRouter.of(context).go(location);
}

/// Dismisses snackbars, as a person swipes them away; one left over sits
/// over the bottom of the screen and takes the taps meant for buttons there.
void clearSnackBars(WidgetTester tester) {
  ScaffoldMessenger.of(tester.element(find.byType(Scaffold).first))
      .clearSnackBars();
}

/// Scrolls the page until [finder] is on screen, then taps it.
Future<void> tapOnScreen(WidgetTester tester, Finder finder) async {
  await tester.scrollUntilVisible(
    finder,
    200,
    scrollable: find.byType(Scrollable).first,
    maxScrolls: 30,
  );
  await tester.pump(const Duration(milliseconds: 300));
  await tester.tap(finder);
  await tester.pump();
}
