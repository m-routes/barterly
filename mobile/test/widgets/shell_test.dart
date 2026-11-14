import 'package:barterly/src/api/token_store.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

import '../helpers.dart';

FakeApi completeTalent() => FakeApi({
  'GET /api/v1/me/': (_) => ok(talentJson),
  'GET /api/v1/profiles/talent/me/': (_) => ok({
    'display_name': 'Asha Rao',
    'bio': 'Muralist from Goa.',
    'talent_type': 'artist',
    'skills': ['mural-painting'],
    'languages': ['en'],
    'home_city': 'Panaji',
    'profile_complete': true,
    'missing_fields': <String>[],
  }),
  'POST /api/v1/auth/logout/': (_) => const FakeResponse(204),
});

void main() {
  testWidgets('complete talent land on Discover with four tabs', (
    tester,
  ) async {
    await pumpApp(
      tester,
      api: completeTalent(),
      tokens: MemoryTokenStore(signedInTokens),
    );
    final bar = find.byType(NavigationBar);
    expect(bar, findsOneWidget);
    for (final label in ['Discover', 'My trips', 'Wallet', 'Profile']) {
      expect(
        find.descendant(of: bar, matching: find.text(label)),
        findsOneWidget,
      );
    }
    expect(find.text('Gigs for you'), findsOneWidget);
    expect(find.text('No gigs right now'), findsOneWidget);
  });

  testWidgets('My trips and Wallet show empty states', (tester) async {
    await pumpApp(
      tester,
      api: completeTalent(),
      tokens: MemoryTokenStore(signedInTokens),
    );
    await tester.tap(find.text('My trips'));
    await tester.pumpAndSettle();
    expect(find.text('No trips yet'), findsOneWidget);
    expect(find.text('Find a gig'), findsOneWidget);
    await tester.tap(find.text('Wallet'));
    await tester.pumpAndSettle();
    expect(find.text('Nothing here yet'), findsOneWidget);
  });

  testWidgets('Profile shows the saved profile and signs out', (tester) async {
    final tokens = MemoryTokenStore(signedInTokens);
    await pumpApp(tester, api: completeTalent(), tokens: tokens);
    await tester.tap(find.text('Profile'));
    await tester.pumpAndSettle();
    expect(find.text('Asha Rao'), findsOneWidget);
    expect(find.text('Artist / muralist'), findsOneWidget);

    await tester.tap(find.text('Sign out'));
    await tester.pumpAndSettle();
    expect(find.text('Sign in to Barterly'), findsOneWidget);
    expect(await tokens.read(), isNull);
  });

  testWidgets('API down at launch offers a retry', (tester) async {
    final api = FakeApi({
      'GET /api/v1/me/': (_) => apiError(502, 'api_unavailable', 'Down.'),
    });
    await pumpApp(tester, api: api, tokens: MemoryTokenStore(signedInTokens));
    expect(find.text("We couldn't load your account"), findsOneWidget);

    api.routes['GET /api/v1/me/'] = (_) => ok(talentJson);
    api.routes['GET /api/v1/profiles/talent/me/'] = (_) =>
        ok(<String, Object?>{});
    await tester.tap(find.text('Try again'));
    await tester.pumpAndSettle();
    expect(find.byType(NavigationBar), findsOneWidget);
  });

  testWidgets('every tap target is at least 48 logical pixels', (tester) async {
    await pumpApp(
      tester,
      api: completeTalent(),
      tokens: MemoryTokenStore(signedInTokens),
    );
    await tester.tap(find.text('Profile'));
    await tester.pumpAndSettle();
    await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
    await expectLater(tester, meetsGuideline(textContrastGuideline));
  });
}
