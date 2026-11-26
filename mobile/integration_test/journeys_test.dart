import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:material_ui/material_ui.dart';

import 'support/acceptance.dart';

/// The talent's side of the core journeys, in the real app against a real API.
/// Starts from `manage.py prepare_journey --talent <persona>`
/// (mobile/tool/acceptance.sh runs it and passes the result in).
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('a talent applies, accepts, signs, shows the pass, hands in and '
      'reviews', (tester) async {
    if (!Acceptance.configured) return markTestSkipped('No acceptance API');
    await launchApp(tester);
    await signIn(tester);

    final title = Acceptance.fixture('gig_to_apply_title');
    await tester.enterText(
      find.widgetWithText(TextField, 'Role, skill or place'),
      title,
    );
    await tester.testTextInput.receiveAction(TextInputAction.search);
    // The result card, not the search box that holds the same words.
    final card = find.descendant(
      of: find.byType(Scrollable),
      matching: find.text(title),
    );
    await waitFor(tester, card);
    await tester.tap(card.first);
    await waitFor(tester, find.text('Apply for this gig'));
    await tester.tap(find.text('Apply for this gig'));
    await waitFor(tester, find.widgetWithText(TextField, 'Your pitch'));
    await tester.enterText(
      find.widgetWithText(TextField, 'Your pitch'),
      'Three seasons at hostel front desks; happy to help with events too.',
    );
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await settle(tester, seconds: 1);
    final agree = find.byType(Checkbox).last;
    await tester.ensureVisible(agree);
    await tester.tap(agree);
    await tester.pump();
    await tester.tap(find.text('Send application'));
    await waitFor(tester, find.textContaining('Application sent'));

    // An offer the host made: accept it and sign with a fresh code.
    go(tester, '/trips/offer/${Acceptance.fixture('offer_application')}');
    await waitFor(tester, find.text('Accept and book'));
    await tapOnScreen(tester, find.text('Accept and book'));
    await waitFor(tester, find.text('Sign version 1'));
    clearSnackBars(tester); // "booked"
    await settle(tester, seconds: 1);
    await tapOnScreen(tester, find.text('Sign version 1'));
    await waitFor(tester, find.textContaining('I have read version 1'));
    await tapOnScreen(tester, find.textContaining('I have read version 1'));
    await tapOnScreen(tester, find.textContaining('Send a code to'));
    await waitFor(tester, find.byType(TextField));
    await tester.enterText(find.byType(TextField).last, Acceptance.code);
    await tapOnScreen(tester, find.widgetWithText(FilledButton, 'Sign'));
    await waitFor(tester, find.textContaining('You: signed'));

    // Arriving today: the pass shows a live code for the host to check.
    go(tester, '/trips/pass/${Acceptance.fixture('booking_arriving_today')}');
    // First time on a device: the app explains before asking for location.
    await waitFor(tester, find.text('Not now'));
    await tester.ensureVisible(find.text('Not now'));
    await tester.pump(const Duration(milliseconds: 300));
    await tester.tap(find.text('Not now'));
    await tester.pump();
    await waitFor(tester, find.textContaining('New code in'));

    // A reel due after the stay: hand it in with the checklist ticked.
    go(
      tester,
      '/trips/deliverables/${Acceptance.fixture('booking_deliverable_due')}',
    );
    await waitFor(tester, find.textContaining('Hand in'));
    await tester.tap(find.textContaining('Hand in').first);
    await waitFor(tester, find.widgetWithText(TextField, "The post's link"));
    await tester.enterText(
      find.widgetWithText(TextField, "The post's link"),
      'https://www.instagram.com/reel/acceptance/',
    );
    await settle(tester, seconds: 1);
    for (final box in find.byType(CheckboxListTile).evaluate().toList()) {
      final finder = find.byWidget(box.widget);
      await tester.ensureVisible(finder);
      await tester.tap(finder);
      await tester.pump();
    }
    // The form's button (the item's own "Hand in" opened it).
    final handIn = find.widgetWithText(FilledButton, 'Hand in').last;
    await tester.ensureVisible(handIn);
    await tester.tap(handIn);
    await waitFor(tester, find.text('Waiting for your host'));

    // A finished stay: review the host.
    go(tester, '/trips/review/${Acceptance.fixture('booking_to_review')}');
    final submit = find.widgetWithText(FilledButton, 'Submit review');
    await waitFor(tester, submit);
    for (final label in [
      'Overall',
      'Communication',
      'Accuracy of the listing',
      'Safety',
      'Payment as agreed',
    ]) {
      await tapOnScreen(tester, find.byTooltip('$label: 5 out of 5'));
    }
    await tester.enterText(
      find.widgetWithText(TextField, 'Your review'),
      'Kind hosts, a clear brief and paid on time. Would go back.',
    );
    await settle(tester, seconds: 1);
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tapOnScreen(tester, submit);
    await waitFor(tester, find.textContaining('Hidden until your host'));
  });
}
