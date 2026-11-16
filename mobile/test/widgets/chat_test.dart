import 'package:barterly/src/api/token_store.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

import '../fixtures.dart';
import '../helpers.dart';

Map<String, Object?> conversationJson({
  bool canSend = true,
  String reason = '',
  bool blocked = false,
}) => {
  'id': 'c1',
  'application': 'a1',
  'gig_title': 'Front desk in Goa',
  'application_status': 'shortlisted',
  'other': {'id': 'v1', 'name': 'Sea Salt Homestay', 'role': 'vendor'},
  'unread': 1,
  'last_message': null,
  'last_message_at': null,
  'opened_at': '2026-11-15T09:00:00Z',
  'can_send': canSend,
  'cant_send_reason': reason,
  'contact_sharing_allowed': false,
  'blocked_by_me': blocked,
};

Map<String, Object?> messageJson(
  int cursor,
  String body, {
  bool mine = false,
  bool masked = false,
}) => {
  'id': 'm$cursor',
  'cursor': '$cursor',
  'sender': mine ? 'me' : 'v1',
  'mine': mine,
  'body': body,
  'masked': masked,
  'attachments': <Object?>[],
  'client_id': '',
  'read_at': null,
  'created_at': '2026-11-15T10:00:00Z',
};

FakeApi chatApi({Map<String, Object?>? conversation, List<String>? reads}) =>
    talentApi({
      'GET /api/v1/applications/mine/': (_) => ok([
        {
          ...applicationJson(status: 'shortlisted'),
          'conversation': 'c1',
          'unread_messages': 1,
        },
      ]),
      'GET /api/v1/conversations/c1/': (_) =>
          ok(conversation ?? conversationJson()),
      'GET /api/v1/conversations/c1/messages/': (request) {
        final after = request.queryParameters['after'];
        return ok({
          'results': after == null
              ? [messageJson(1, 'Hi! When can you start?')]
              : <Object?>[],
          'cursor': '${after ?? 1}',
          'has_earlier': false,
          'other_read_up_to': '0',
        });
      },
      'POST /api/v1/conversations/c1/read/': (request) {
        reads?.add('${(request.data as Map)['up_to']}');
        return ok({'marked': 1});
      },
      'POST /api/v1/conversations/c1/messages/': (request) =>
          FakeResponse(201, {
            'message': messageJson(2, '[hidden] me', mine: true, masked: true),
            'notice':
                'We hid an off-platform contact. Contact details can be '
                'shared once the booking is confirmed.',
          }),
    });

Future<void> openChat(WidgetTester tester, FakeApi api) async {
  usePhoneScreen(tester);
  await pumpApp(tester, api: api, tokens: MemoryTokenStore(signedInTokens));
  await tester.tap(find.text('My trips'));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Message (1 new)'));
  await tester.pumpAndSettle();
}

/// Leave the chat so its polling timer stops.
Future<void> leaveChat(WidgetTester tester) async {
  await tester.pageBack();
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('opens the chat from My trips, reads and replies', (
    tester,
  ) async {
    final reads = <String>[];
    final api = chatApi(reads: reads);
    await openChat(tester, api);

    expect(find.text('Sea Salt Homestay'), findsOneWidget);
    expect(find.text('Hi! When can you start?'), findsOneWidget);
    expect(find.textContaining('hidden until the booking'), findsOneWidget);
    expect(reads, ['1']);

    await tester.enterText(find.byType(TextField), 'WhatsApp me');
    await tester.tap(find.byTooltip('Send'));
    await tester.pumpAndSettle();
    expect(find.text('[hidden] me'), findsOneWidget);
    expect(find.byKey(const Key('chat-notice')), findsOneWidget);
    final sent = api.requests.lastWhere(
      (r) => r.method == 'POST' && r.path.endsWith('/messages/'),
    );
    expect((sent.data as Map)['body'], 'WhatsApp me');
    expect((sent.data as Map)['client_id'], isNotEmpty);

    // While open, it polls after the cursor.
    await tester.pump(const Duration(seconds: 5));
    final polls = api.requests.where(
      (r) => r.path.endsWith('/messages/') && r.method == 'GET',
    );
    expect(polls.last.queryParameters['after'], isNotNull);

    await leaveChat(tester);
    final pollsBefore = api.requests.length;
    await tester.pump(const Duration(seconds: 20));
    expect(
      api.requests.skip(pollsBefore).where((r) => r.path.contains('/c1/')),
      isEmpty,
      reason: 'no polling once the chat screen is closed',
    );
  });

  testWidgets('a closed chat says why and has no composer', (tester) async {
    final api = chatApi(
      conversation: conversationJson(
        canSend: false,
        reason: 'This application is closed, so the chat is read-only.',
      ),
    );
    await openChat(tester, api);
    expect(find.textContaining('read-only'), findsOneWidget);
    expect(find.byType(TextField), findsNothing);
    await leaveChat(tester);
  });

  testWidgets('reports a message with a reason', (tester) async {
    final api = chatApi()
      ..routes['POST /api/v1/messages/m1/report/'] = (_) =>
          const FakeResponse(201, {'id': 'r1', 'status': 'open'});
    await openChat(tester, api);
    await tester.tap(find.text('Report'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Scam or fraud'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Our team will review'), findsOneWidget);
    final report = api.requests.lastWhere((r) => r.path.endsWith('/report/'));
    expect((report.data as Map)['reason'], 'scam');
    await leaveChat(tester);
  });
}
