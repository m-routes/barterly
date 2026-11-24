import 'package:barterly/src/platform/network_status.dart';
import 'package:barterly/src/providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:material_ui/material_ui.dart';

import 'support/acceptance.dart';

/// Failure scenarios from the talent's side, in the real app against a real
/// API. (Server-side scenarios: backend/apps/qa/tests/test_failure_scenarios.py;
/// a lost answer during apply: test/apply/outbox_test.dart.)
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('an application written offline is kept and sent when the '
      'network returns', (tester) async {
    if (!Acceptance.configured) return markTestSkipped('No acceptance API');
    final network = FakeNetworkStatus();
    await launchApp(tester, network: network);
    await signIn(tester);

    final title = Acceptance.fixture('gig_to_apply_offline_title');
    await tester.enterText(
      find.widgetWithText(TextField, 'Role, skill or place'),
      title,
    );
    await tester.testTextInput.receiveAction(TextInputAction.search);
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
      'Written on a bus through the ghats with no signal at all.',
    );
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await settle(tester, seconds: 1);

    network.online = false; // the signal drops
    await tapOnScreen(tester, find.byType(Checkbox).last);
    await tapOnScreen(tester, find.text('Send application'));
    await waitFor(tester, find.textContaining("You're offline"));

    network.online = true; // and comes back: the outbox sends it
    clearSnackBars(tester);
    go(tester, '/trips');
    await waitFor(tester, find.text(title));

    // On the server, not just in the outbox.
    final container = ProviderScope.containerOf(
      tester.element(find.byType(Scaffold).first),
    );
    final mine = await container.read(applicationsRepositoryProvider).mine();
    expect(mine.map((a) => a.gigTitle), contains(title));
  });
}
