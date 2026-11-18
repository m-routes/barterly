import 'package:barterly/src/api/token_store.dart';
import 'package:barterly/src/platform/calendar.dart';
import 'package:barterly/src/providers.dart';
import 'package:barterly/src/trips/trip_screen.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

import '../fixtures.dart';
import '../helpers.dart';
import 'agreements_test.dart' show agreementJson;

class FakeCalendar implements CalendarService {
  final added = <CalendarEvent>[];

  @override
  Future<bool> add(CalendarEvent event) async {
    added.add(event);
    return true;
  }
}

Map<String, Object?> interviewJson(String status) => {
  'id': 'i1',
  'status': status,
  'slots': [
    {
      'id': 7,
      'starts_at': '2026-11-20T10:30:00Z',
      'starts_at_ist': 'Fri 20 Nov, 4:00 pm',
    },
    {
      'id': 8,
      'starts_at': '2026-11-21T05:30:00Z',
      'starts_at_ist': 'Sat 21 Nov, 11:00 am',
    },
  ],
  'starts_at': status == 'scheduled' ? '2026-11-20T10:30:00Z' : null,
  'starts_at_ist': status == 'scheduled' ? 'Fri 20 Nov, 4:00 pm' : '',
  'duration_minutes': 30,
  'video_link': status == 'scheduled' ? 'https://meet.google.com/abc' : '',
  'note': 'Looking forward to it',
};

Map<String, Object?> detailJson({
  String status = 'interview',
  Map<String, Object?>? interview,
  String? agreement,
}) => {
  ...applicationJson(status: status),
  'agreement': agreement,
  'conversation': 'c1',
  'timeline': [
    {'status': 'applied', 'at': '2026-11-10T10:00:00Z', 'reason': ''},
    {
      'status': status,
      'at': '2026-11-12T10:00:00Z',
      'reason': 'Loved your pitch',
    },
  ],
  'interview': interview,
};

Future<void> openTrip(
  WidgetTester tester,
  FakeApi api, {
  FakeCalendar? calendar,
  Map<String, Object?>? listItem,
}) async {
  usePhoneScreen(tester);
  await pumpApp(
    tester,
    api: api,
    tokens: MemoryTokenStore(signedInTokens),
    extra: [if (calendar != null) calendarProvider.overrideWithValue(calendar)],
  );
  await tester.tap(find.text('My trips'));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Trip details'));
  await tester.pumpAndSettle();
}

/// The tracker read out to screen readers, as its Semantics label says.
Finder trackerLabelled(String label) => find.descendant(
  of: find.byType(TripScreen),
  matching: find.byWidgetPredicate(
    (w) => w is Semantics && w.properties.label == label,
  ),
);

void main() {
  testWidgets('the tracker, what is next, and the status timeline', (
    tester,
  ) async {
    final api = talentApi({
      'GET /api/v1/applications/mine/': (_) =>
          ok([applicationJson(status: 'shortlisted')]),
      'GET /api/v1/applications/a1/': (_) =>
          ok(detailJson(status: 'shortlisted')),
    });
    await openTrip(tester, api);

    expect(find.byType(TripScreen), findsOneWidget);
    expect(
      trackerLabelled('Progress: Shortlisted, 2 of 7 steps done'),
      findsOneWidget,
    );
    expect(find.textContaining("You're shortlisted"), findsOneWidget);
    expect(find.text('Loved your pitch'), findsOneWidget);
    expect(find.text('Applied'), findsWidgets);
    expect(find.text('Message the host'), findsOneWidget);
  });

  testWidgets('picks an interview time', (tester) async {
    var picked = false;
    final api = talentApi({
      'GET /api/v1/applications/mine/': (_) =>
          ok([applicationJson(status: 'interview')]),
      'GET /api/v1/applications/a1/': (_) => ok(
        detailJson(interview: interviewJson(picked ? 'scheduled' : 'proposed')),
      ),
      'POST /api/v1/applications/a1/interview/pick/': (_) {
        picked = true;
        return ok(interviewJson('scheduled'));
      },
    });
    await openTrip(tester, api);

    expect(find.text('Pick a time that works (India time).'), findsOneWidget);
    final book = find.widgetWithText(FilledButton, 'Book this time');
    expect(tester.widget<FilledButton>(book).onPressed, isNull);
    await tester.tap(find.text('Sat 21 Nov, 11:00 am'));
    await tester.pumpAndSettle();
    await tester.tap(book);
    await tester.pumpAndSettle();

    final sent = api.requests.lastWhere((r) => r.path.endsWith('/pick/'));
    expect(sent.data, {'slot_id': 8});
    expect(find.text('Fri 20 Nov, 4:00 pm · 30 minutes'), findsOneWidget);
    expect(find.text('Join the call'), findsOneWidget);
  });

  testWidgets('asks for other interview times', (tester) async {
    final api = talentApi({
      'GET /api/v1/applications/mine/': (_) =>
          ok([applicationJson(status: 'interview')]),
      'GET /api/v1/applications/a1/': (_) =>
          ok(detailJson(interview: interviewJson('proposed'))),
      'POST /api/v1/applications/a1/interview/new-times/': (_) =>
          ok(interviewJson('new_times_requested')),
    });
    await openTrip(tester, api);
    await tester.tap(find.text('None of these work'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'Weekends are best');
    await tester.tap(find.text('Ask the host'));
    await tester.pumpAndSettle();
    final sent = api.requests.lastWhere((r) => r.path.endsWith('/new-times/'));
    expect(sent.data, {'note': 'Weekends are best'});
  });

  testWidgets('adds the interview and check-in to the calendar', (
    tester,
  ) async {
    final calendar = FakeCalendar();
    final api = talentApi({
      'GET /api/v1/applications/mine/': (_) =>
          ok([applicationJson(status: 'confirmed')]),
      'GET /api/v1/applications/a1/': (_) => ok(
        detailJson(
          status: 'confirmed',
          interview: interviewJson('scheduled'),
          agreement: 'ag1',
        ),
      ),
      'GET /api/v1/agreements/ag1/': (_) =>
          ok(agreementJson(signed: true, bookingStatus: 'confirmed')),
    });
    await openTrip(tester, api, calendar: calendar);

    expect(
      trackerLabelled('Progress: Signed, 5 of 7 steps done'),
      findsOneWidget,
    );
    await tester.tap(find.text('Add to calendar'));
    await tester.pumpAndSettle();
    final interview = calendar.added.single;
    expect(
      interview.title,
      'Barterly interview: Reception and social media volunteer',
    );
    expect(interview.start, DateTime.parse('2026-11-20T10:30:00Z').toLocal());
    expect(
      interview.end.difference(interview.start),
      const Duration(minutes: 30),
    );
    expect(interview.remindBefore, const Duration(minutes: 30));
    expect(interview.url, 'https://meet.google.com/abc');

    // Into the middle of the screen, clear of the bottom navigation bar.
    await Scrollable.ensureVisible(
      tester.element(find.text('Add check-in to calendar')),
      alignment: 0.5,
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Add check-in to calendar'));
    await tester.pumpAndSettle();
    expect(calendar.added, hasLength(2));
    final checkIn = calendar.added.last;
    expect(checkIn.allDay, isTrue);
    expect(checkIn.start, DateTime(2026, 12, 15));
    expect(checkIn.remindBefore, const Duration(days: 1));
  });
}
