import 'package:barterly/src/api/token_store.dart';
import 'package:barterly/src/profile/validators.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

import '../helpers.dart';

Finder field(String label) => find.widgetWithText(TextFormField, label);

/// A signed-in talent without a profile, on the setup screen.
Future<FakeApi> openSetup(WidgetTester tester, {Handler? onSave}) async {
  var complete = false;
  final api = FakeApi({
    'GET /api/v1/me/': (_) => ok(userJson(complete: complete)),
    'GET /api/v1/profiles/talent/me/': (_) =>
        apiError(404, 'profile_not_found'),
    'GET /api/v1/profiles/skills/': (_) => ok(skillsJson),
    'PATCH /api/v1/profiles/talent/me/':
        onSave ??
        (r) {
          complete = true;
          return ok({
            ...r.data! as Map<String, Object?>,
            'profile_complete': true,
          });
        },
  });
  tester.view.physicalSize = const Size(1170, 2532);
  tester.view.devicePixelRatio = 3;
  addTearDown(tester.view.reset);
  await pumpApp(tester, api: api, tokens: MemoryTokenStore(signedInTokens));
  expect(find.text('Set up your profile'), findsOneWidget);
  return api;
}

Future<void> tapFinish(WidgetTester tester) async {
  final button = find.widgetWithText(FilledButton, 'Finish setup');
  await scrollTo(tester, button);
  await tester.tap(button);
  await tester.pumpAndSettle();
}

/// Scrolls the form until [finder] is on screen, starting from the top if it
/// isn't built yet (the list is lazy, and errors may be above the button).
Future<void> scrollTo(WidgetTester tester, Finder finder) async {
  final list = find.byType(Scrollable).first;
  if (finder.evaluate().isEmpty) {
    await tester.fling(list, const Offset(0, 20000), 10000);
    await tester.pumpAndSettle();
  }
  await tester.scrollUntilVisible(finder, 200, scrollable: list);
}

Future<void> pickDob(WidgetTester tester, DateTime date) async {
  await scrollTo(tester, find.text('Choose a date'));
  await tester.tap(find.text('Choose a date'));
  await tester.pumpAndSettle();
  final input = find.byType(TextField).last;
  await tester.enterText(
    input,
    '${date.month.toString().padLeft(2, '0')}/'
    '${date.day.toString().padLeft(2, '0')}/${date.year}',
  );
  await tester.tap(find.text('OK'));
  await tester.pumpAndSettle();
}

Future<void> fillValid(WidgetTester tester) async {
  await tester.enterText(field('Display name'), 'Asha Rao');
  await tester.tap(find.text('What do you do?'));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Artist / muralist').last);
  await tester.pumpAndSettle();
  await tester.enterText(field('Bio'), 'Muralist from Goa.');
  await tester.enterText(field('Home city'), 'Panaji');
  await pickDob(tester, DateTime(2000, 6, 15));
  await scrollTo(tester, find.text('Mural painting'));
  await tester.tap(find.text('Mural painting'));
  await scrollTo(tester, find.text('Hindi'));
  await tester.tap(find.text('English'));
  await tester.tap(find.text('Hindi'));
  await tester.pump();
  await scrollTo(tester, field('Their name'));
  await tester.enterText(field('Their name'), 'Ravi Rao');
  await tester.enterText(field('Their phone number'), '98111 11111');
}

void main() {
  testWidgets('every required field explains itself', (tester) async {
    final api = await openSetup(tester);
    await tapFinish(tester);

    await scrollTo(tester, find.text('Enter the name hosts will see.'));
    expect(find.text('Enter the name hosts will see.'), findsOneWidget);
    for (final message in [
      'Choose what you do.',
      'Enter a short bio.',
      'Enter your home city.',
      'Enter your date of birth.',
      'Pick at least one skill.',
      'Pick at least one language.',
      "Enter your emergency contact's name.",
      "Enter your emergency contact's phone number.",
    ]) {
      await scrollTo(tester, find.text(message));
      expect(find.text(message), findsOneWidget, reason: message);
    }
    expect(api.calls.where((c) => c.startsWith('PATCH')), isEmpty);
  });

  testWidgets("the date picker won't offer an under-18 date", (tester) async {
    await openSetup(tester);
    await scrollTo(tester, find.text('Choose a date'));
    await tester.tap(find.text('Choose a date'));
    await tester.pumpAndSettle();
    final picker = tester.widget<DatePickerDialog>(
      find.byType(DatePickerDialog),
    );
    expect(picker.lastDate, latestAdultBirthday());
  });

  testWidgets("the emergency number can't be your own", (tester) async {
    await openSetup(tester);
    await scrollTo(tester, field('Their phone number'));
    await tester.enterText(field('Their phone number'), '98765 43210');
    await tester.pump();
    expect(
      find.text("Use someone else's number, not your own."),
      findsOneWidget,
    );
  });

  testWidgets('a valid form saves and opens the app', (tester) async {
    final api = await openSetup(tester);
    await fillValid(tester);
    await tapFinish(tester);

    final patch = api.requests.firstWhere((r) => r.method == 'PATCH');
    expect(Map.of(patch.data as Map)..remove('languages'), {
      'display_name': 'Asha Rao',
      'bio': 'Muralist from Goa.',
      'talent_type': 'artist',
      'skills': ['mural-painting'],
      'home_city': 'Panaji',
      'emergency_contact_name': 'Ravi Rao',
      'emergency_contact_phone': '+919811111111',
      'date_of_birth': '2000-06-15',
      'instagram_handle': '',
    });
    expect((patch.data as Map)['languages'], unorderedEquals(['en', 'hi']));
    // Profile complete: the bottom bar appears.
    expect(find.byType(NavigationBar), findsOneWidget);
  });

  testWidgets('server field errors land on their fields', (tester) async {
    await openSetup(
      tester,
      onSave: (_) => apiError(400, 'validation_error', 'Invalid input.', {
        'home_city': ['Not a city we know.'],
      }),
    );
    await fillValid(tester);
    await tapFinish(tester);

    expect(
      find.text('Some details need fixing. Check the highlighted fields.'),
      findsOneWidget,
    );
    await scrollTo(tester, find.text('Not a city we know.'));
    expect(find.text('Not a city we know.'), findsOneWidget);
  });
}
