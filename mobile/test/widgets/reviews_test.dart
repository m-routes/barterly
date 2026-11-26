import 'package:barterly/src/api/token_store.dart';
import 'package:barterly/src/reviews/review_screens.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

import '../fixtures.dart';
import '../helpers.dart';
import 'agreements_test.dart' show agreementJson;
import 'trips_test.dart' show detailJson;

const labels = {
  'communication': 'Communication',
  'accuracy': 'Accuracy of the listing',
  'safety': 'Safety',
  'reliability': 'Payment as agreed',
};

Map<String, Object?> reviewJson({
  String id = 'r1',
  int rating = 5,
  String status = 'published',
  Map<String, Object?>? reply,
}) => {
  'id': id,
  'booking_id': 'b1',
  'subject_side': 'talent',
  'rating': rating,
  'categories': [
    {'key': 'communication', 'label': 'Communication', 'score': 5},
    {'key': 'accuracy', 'label': 'Quality of the work', 'score': 4},
    {'key': 'safety', 'label': 'Safety', 'score': 5},
    {'key': 'reliability', 'label': 'Punctuality', 'score': 5},
  ],
  'text': 'Painted a lovely mural and was great with guests.',
  'status': status,
  'author_name': 'Sea Breeze Hostel',
  'submitted_at': '2026-12-21T10:00:00Z',
  'published_at': status == 'published' ? '2026-12-22T10:00:00Z' : null,
  'reply': reply,
};

Map<String, Object?> bookingReviews({
  bool canReview = true,
  Map<String, Object?>? mine,
  Map<String, Object?>? theirs,
  bool theyHaveReviewed = false,
}) => {
  'reviewing': 'host',
  'can_review': canReview,
  'window_closes_at': '2027-01-03T10:00:00Z',
  'category_labels': labels,
  'mine': mine,
  'theirs': theirs,
  'they_have_reviewed': theyHaveReviewed,
};

FakeApi completedStay(Map<String, Handler> more) => talentApi({
  'GET /api/v1/applications/mine/': (_) =>
      ok([applicationJson(status: 'confirmed')]),
  'GET /api/v1/applications/a1/': (_) =>
      ok(detailJson(status: 'confirmed', agreement: 'ag1')),
  'GET /api/v1/agreements/ag1/': (_) =>
      ok(agreementJson(signed: true, bookingStatus: 'completed')),
  ...more,
});

Future<void> openReview(WidgetTester tester, FakeApi api) async {
  usePhoneScreen(tester);
  await pumpApp(tester, api: api, tokens: MemoryTokenStore(signedInTokens));
  await tester.tap(find.text('My trips'));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Trip details'));
  await tester.pumpAndSettle();
  final button = find.text('Review your host');
  await Scrollable.ensureVisible(tester.element(button), alignment: 0.5);
  await tester.pumpAndSettle();
  await tester.tap(button);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('reviews the host once every score and enough words are in', (
    tester,
  ) async {
    Map<String, Object?>? sent;
    var submitted = false;
    final api = completedStay({
      'GET /api/v1/bookings/b1/reviews/': (_) => ok(
        submitted
            ? bookingReviews(
                canReview: false,
                mine: reviewJson(status: 'submitted'),
              )
            : bookingReviews(theyHaveReviewed: true),
      ),
      'POST /api/v1/bookings/b1/reviews/': (request) {
        sent = Map<String, Object?>.from(request.data as Map);
        submitted = true;
        return FakeResponse(201, reviewJson(status: 'submitted'));
      },
    });
    await openReview(tester, api);

    expect(find.byType(StayReviewScreen), findsOneWidget);
    expect(find.textContaining('Your host has reviewed you'), findsOneWidget);
    final submit = find.widgetWithText(FilledButton, 'Submit review');
    expect(tester.widget<FilledButton>(submit).onPressed, isNull);
    for (final label in ['Overall', ...labels.values]) {
      final star = find.byTooltip('$label: 5 out of 5');
      await tester.ensureVisible(star);
      await tester.tap(star);
      await tester.pump();
    }
    await tester.enterText(
      find.widgetWithText(TextField, 'Your review'),
      'Warm welcome, clear tasks and paid on time.',
    );
    await tester.pumpAndSettle();
    await tester.ensureVisible(submit);
    await tester.tap(submit);
    await tester.pumpAndSettle();
    expect(sent, {
      'rating': 5,
      'communication': 5,
      'accuracy': 5,
      'safety': 5,
      'reliability': 5,
      'text': 'Warm welcome, clear tasks and paid on time.',
    });
    expect(
      find.textContaining('Hidden until your host reviews too'),
      findsOneWidget,
    );
  });

  testWidgets("shows the host's published review and replies once", (
    tester,
  ) async {
    Map<String, Object?>? reply;
    final api = completedStay({
      'GET /api/v1/bookings/b1/reviews/': (_) => ok(
        bookingReviews(
          canReview: false,
          mine: reviewJson(id: 'r0'),
          theirs: reply == null
              ? reviewJson()
              : reviewJson(
                  reply: {'text': reply!['text'], 'created_at': '2026-12-23'},
                ),
        ),
      ),
      'POST /api/v1/reviews/r1/reply/': (request) {
        reply = Map<String, Object?>.from(request.data as Map);
        return FakeResponse(201, {'text': reply!['text']});
      },
    });
    await openReview(tester, api);

    expect(find.text("Your host's review of you"), findsOneWidget);
    expect(find.text('Punctuality: 5/5'), findsNWidgets(2)); // yours and theirs
    final replyButton = find.widgetWithText(TextButton, 'Reply');
    await tester.ensureVisible(replyButton);
    await tester.tap(replyButton);
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'Thank you!');
    await tester.pumpAndSettle();
    await tester.tap(find.text('Post reply'));
    await tester.pumpAndSettle();
    expect(reply, {'text': 'Thank you!'});
    expect(find.text('Reply: Thank you!'), findsOneWidget);
    expect(find.widgetWithText(TextButton, 'Reply'), findsNothing);
  });

  testWidgets('shows your reputation and the reviews hosts left', (
    tester,
  ) async {
    final api = talentApi({
      'GET /api/v1/users/${talentJson['id']}/reputation/': (_) => ok({
        'talent': {
          'rating_average': '4.80',
          'review_count': 5,
          'completion_rate': 100,
          'response_minutes': 25,
          'badges': [
            {'key': 'top_volunteer', 'label': 'Top Volunteer'},
          ],
        },
        'host': {
          'rating_average': null,
          'review_count': 0,
          'completion_rate': null,
          'response_minutes': null,
          'badges': <Object?>[],
        },
      }),
      'GET /api/v1/users/${talentJson['id']}/reviews/': (_) => ok({
        'count': 1,
        'next': null,
        'previous': null,
        'results': [reviewJson()],
      }),
    });
    usePhoneScreen(tester);
    await pumpApp(tester, api: api, tokens: MemoryTokenStore(signedInTokens));
    await tester.tap(find.text('Profile'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Reviews and reputation'));
    await tester.pumpAndSettle();

    expect(find.byType(MyReviewsScreen), findsOneWidget);
    expect(find.text('★ 4.8 from 5 reviews'), findsOneWidget);
    expect(find.text('100% of stays completed'), findsOneWidget);
    expect(find.text('You reply in about 25 min'), findsOneWidget);
    expect(find.text('Top Volunteer'), findsOneWidget);
    expect(find.text('Sea Breeze Hostel'), findsOneWidget);
  });
}
