import 'package:barterly/src/api/token_store.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

import '../helpers.dart';

Finder field(String label) => find.widgetWithText(TextField, label);

Map<String, Object?> ticketJson({
  String status = 'open',
  List<Map<String, Object?>> messages = const [],
}) => {
  'id': 't-1',
  'reference': 'S-T1',
  'kind': 'bug',
  'subject': "Reel won't upload",
  'status': status,
  'booking': null,
  'created_at': '2026-11-24T04:30:00Z',
  'last_message_at': '2026-11-24T04:30:00Z',
  'reply_expected_by': status == 'open' ? '2026-11-25T04:30:00Z' : null,
  'messages': messages,
};

Future<void> openHelp(WidgetTester tester, FakeApi api) async {
  usePhoneScreen(tester);
  await pumpApp(tester, api: api, tokens: MemoryTokenStore(signedInTokens));
  await tester.tap(find.text('Profile'));
  await tester.pumpAndSettle();
  await tester.scrollUntilVisible(
    find.text('Help and feedback'),
    200,
    scrollable: find.byType(Scrollable).last,
  );
  await tester.tap(find.text('Help and feedback'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('sends a request and opens it', (tester) async {
    Object? sent;
    var tickets = <Object?>[];
    final api = talentApi({
      'GET /api/v1/support/tickets/': (_) => ok(tickets),
      'POST /api/v1/support/tickets/': (r) {
        sent = r.data;
        tickets = [ticketJson()];
        return FakeResponse(
          201,
          ticketJson(
            messages: [
              {
                'id': 1,
                'from_staff': false,
                'body': 'It stops at 90%.',
                'created_at': '2026-11-24T04:30:00Z',
              },
            ],
          ),
        );
      },
      'GET /api/v1/support/tickets/t-1/': (_) => ok(
        ticketJson(
          messages: [
            {
              'id': 1,
              'from_staff': false,
              'body': 'It stops at 90%.',
              'created_at': '2026-11-24T04:30:00Z',
            },
          ],
        ),
      ),
    });
    await openHelp(tester, api);
    expect(find.text('No requests yet'), findsOneWidget);

    await tester.tap(find.text('Write to us'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Send'));
    await tester.pump();
    expect(find.text("Choose what it's about."), findsOneWidget);

    await tester.tap(find.text("Something isn't working"));
    await tester.enterText(field('Title'), "Reel won't upload");
    await tester.enterText(field('Message'), 'It stops at 90%.');
    await tester.ensureVisible(find.text('Send'));
    await tester.tap(find.text('Send'));
    await tester.pumpAndSettle();

    expect(sent, {
      'kind': 'bug',
      'subject': "Reel won't upload",
      'body': 'It stops at 90%.',
      'screen': 'profile/help',
      'platform': 'android',
    });
    expect(find.text('It stops at 90%.'), findsOneWidget);
    expect(find.textContaining('We aim to answer by'), findsOneWidget);
  });

  testWidgets('shows support replies and lets the person write back', (
    tester,
  ) async {
    Object? replied;
    final api = talentApi({
      'GET /api/v1/support/tickets/': (_) =>
          ok([ticketJson(status: 'waiting')]),
      'GET /api/v1/support/tickets/t-1/': (_) => ok(
        ticketJson(
          status: 'waiting',
          messages: [
            {
              'id': 2,
              'from_staff': true,
              'body': 'Try again on Wi-Fi.',
              'created_at': '2026-11-24T05:00:00Z',
            },
          ],
        ),
      ),
      'POST /api/v1/support/tickets/t-1/messages/': (r) {
        replied = r.data;
        return FakeResponse(201, ticketJson());
      },
    });
    await openHelp(tester, api);
    expect(find.textContaining("We've answered"), findsOneWidget);
    await tester.tap(find.text("Reel won't upload"));
    await tester.pumpAndSettle();
    expect(find.text('Try again on Wi-Fi.'), findsOneWidget);
    await tester.enterText(field('Reply'), 'Worked, thanks!');
    await tester.ensureVisible(find.text('Send'));
    await tester.tap(find.text('Send'));
    await tester.pumpAndSettle();
    expect(replied, {'body': 'Worked, thanks!'});
  });
}
