import 'package:barterly/src/api/token_store.dart';
import 'package:barterly/src/deliverables/deliverables_screen.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

import '../fixtures.dart';
import '../helpers.dart';
import 'agreements_test.dart' show agreementJson;
import 'trips_test.dart' show detailJson;

Map<String, Object?> deliverableJson({
  String id = 'd1',
  String title = 'Instagram reel 1 of 2',
  String status = 'pending',
  bool disclosure = true,
  Map<String, Object?>? latest,
  List<Map<String, Object?>> stats = const [],
}) => {
  'id': id,
  'booking_id': 'b1',
  'gig_title': 'Rooftop café reels',
  'kind': 'reel',
  'platform': 'instagram',
  'spec_type': 'instagram_reel',
  'title': title,
  'notes': 'Show the rooftop',
  'due_date': '2026-12-20',
  'status': status,
  'change_rounds': 1,
  'change_rounds_left': 1,
  'disclosure_required': disclosure,
  'submitted_at': null,
  'approved_at': null,
  'latest_submission': latest,
  'stats': stats,
  'usage_rights': null,
  'usable_until': null,
};

Future<void> openDeliverables(
  WidgetTester tester,
  FakeApi api, {
  FakeMediaPicker? picker,
}) async {
  usePhoneScreen(tester);
  await pumpApp(
    tester,
    api: api,
    tokens: MemoryTokenStore(signedInTokens),
    picker: picker,
  );
  await tester.tap(find.text('My trips'));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Trip details'));
  await tester.pumpAndSettle();
  final button = find.text('Deliverables');
  await Scrollable.ensureVisible(tester.element(button), alignment: 0.5);
  await tester.pumpAndSettle();
  await tester.tap(button);
  await tester.pumpAndSettle();
}

FakeApi stayApi(Map<String, Handler> more) => talentApi({
  'GET /api/v1/applications/mine/': (_) =>
      ok([applicationJson(status: 'confirmed')]),
  'GET /api/v1/applications/a1/': (_) =>
      ok(detailJson(status: 'confirmed', agreement: 'ag1')),
  'GET /api/v1/agreements/ag1/': (_) =>
      ok(agreementJson(signed: true, bookingStatus: 'delivering')),
  ...more,
});

void main() {
  testWidgets('hands a post in once the collaboration label is confirmed', (
    tester,
  ) async {
    Map<String, Object?>? sent;
    final api = stayApi({
      'GET /api/v1/bookings/b1/deliverables/items/': (_) => ok([
        deliverableJson(
          status: 'changes_requested',
          latest: {
            'version': 1,
            'post_url': '',
            'files': <Object?>[],
            'review': 'changes',
            'review_note': 'Brighter colours please',
          },
        ),
      ]),
      'POST /api/v1/deliverables/items/d1/submit/': (request) {
        sent = Map<String, Object?>.from(request.data as Map);
        return FakeResponse(201, deliverableJson(status: 'submitted'));
      },
    });
    await openDeliverables(tester, api);

    expect(find.byType(DeliverablesScreen), findsOneWidget);
    expect(find.text('Changes asked for'), findsWidgets);
    expect(find.text('Your host: Brighter colours please'), findsOneWidget);
    expect(
      find.text('Your host can ask for changes 1 more time(s).'),
      findsOneWidget,
    );
    // The brief: where, when, and the host's notes.
    expect(find.text('Post on Instagram, due Sun 20 Dec'), findsOneWidget);
    expect(find.text('“Show the rooftop”'), findsOneWidget);
    await tester.tap(find.text('Hand in again'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextField, "The post's link"),
      'https://www.instagram.com/reel/Cabc/',
    );
    await tester.pumpAndSettle();
    final handIn = find.widgetWithText(FilledButton, 'Hand in');
    expect(tester.widget<FilledButton>(handIn).onPressed, isNull);
    // The checklist: every box, before it can go.
    for (final item in [
      'It matches the brief',
      'The post is public and the link opens',
      'The post has the collaboration label',
    ]) {
      final box = find.ancestor(
        of: find.textContaining(item),
        matching: find.byType(CheckboxListTile),
      );
      await tester.ensureVisible(box);
      expect(tester.widget<FilledButton>(handIn).onPressed, isNull);
      await tester.tap(box);
      await tester.pumpAndSettle();
    }
    await tester.ensureVisible(handIn);
    await tester.tap(handIn);
    await tester.pumpAndSettle();
    expect(sent, {
      'post_url': 'https://www.instagram.com/reel/Cabc/',
      'file_ids': <String>[],
      'note': '',
      'disclosure_confirmed': true,
    });
  });

  testWidgets('adds self-reported numbers with a screenshot', (tester) async {
    Map<String, Object?>? reported;
    final picker = FakeMediaPicker()..addPhoto('numbers.jpg');
    final api = stayApi({
      'GET /api/v1/bookings/b1/deliverables/items/': (_) => ok([
        deliverableJson(
          status: 'submitted',
          stats: [
            {
              'source': 'instagram',
              'self_reported': false,
              'views': 1500,
              'likes': 90,
              'comments': 4,
            },
          ],
        ),
      ]),
      'POST /api/v1/media/upload-url/': (_) =>
          FakeResponse(201, uploadTicket('m1')),
      'PUT https://storage.test/upload/m1': (_) => const FakeResponse(200),
      'POST /api/v1/media/confirm/': (_) => ok({'id': 'm1'}),
      'POST /api/v1/deliverables/items/d1/stats/': (request) {
        reported = Map<String, Object?>.from(request.data as Map);
        return const FakeResponse(201, {
          'source': 'manual',
          'self_reported': true,
        });
      },
    });
    await openDeliverables(tester, api, picker: picker);

    expect(
      find.text('From instagram: 1,500 views · 90 likes · 4 comments'),
      findsOneWidget,
    );
    await tester.tap(find.text('Add your numbers'));
    await tester.pumpAndSettle();
    final save = find.widgetWithText(FilledButton, 'Save numbers');
    await tester.enterText(find.widgetWithText(TextField, 'Views'), '2,000');
    await tester.pumpAndSettle();
    expect(
      tester.widget<FilledButton>(save).onPressed,
      isNull,
    ); // no screenshot
    await tester.tap(find.text('Add a screenshot'));
    await tester.pumpAndSettle();
    await tester.tap(save);
    await tester.pumpAndSettle();
    expect(reported, {
      'views': 2000,
      'likes': null,
      'comments': null,
      'screenshot_id': 'm1',
    });
  });

  testWidgets('says when there is nothing to hand in', (tester) async {
    final api = stayApi({
      'GET /api/v1/bookings/b1/deliverables/items/': (_) => ok(<Object?>[]),
    });
    await openDeliverables(tester, api);
    expect(find.textContaining('Nothing to hand in'), findsOneWidget);
  });
}
