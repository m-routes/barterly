import 'package:barterly/src/api/token_store.dart';
import 'package:barterly/src/attendance/location.dart';
import 'package:barterly/src/attendance/pass_screen.dart';
import 'package:barterly/src/platform/key_value_store.dart';
import 'package:barterly/src/providers.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:qr_flutter/qr_flutter.dart';

import '../fixtures.dart';
import '../helpers.dart';
import 'agreements_test.dart' show agreementJson;
import 'trips_test.dart' show detailJson;

const secret = 'JBSWY3DPEHPK3PXP';
final now = DateTime.utc(2026, 12, 1, 10);

Map<String, Object?> passJson() => {
  'booking_id': 'b1',
  'token': 'BRT1.payload.signature',
  'code_secret': secret,
  'code_period_seconds': 300,
  'code_digits': 6,
  'valid_from': '2026-11-30T18:30:00Z',
  'valid_until': '2026-12-02T18:30:00Z',
};

class FakeLocation implements LocationReader {
  @override
  Future<Located?> current() async =>
      const Located(latitude: 15.5, longitude: 73.8, accuracyM: 12);
}

FakeApi tripApi(String bookingStatus, [Map<String, Handler>? more]) =>
    talentApi({
      'GET /api/v1/applications/mine/': (_) =>
          ok([applicationJson(status: 'confirmed')]),
      'GET /api/v1/applications/a1/': (_) =>
          ok(detailJson(status: 'confirmed', agreement: 'ag1')),
      'GET /api/v1/agreements/ag1/': (_) =>
          ok(agreementJson(signed: true, bookingStatus: bookingStatus)),
      ...?more,
    });

Future<void> openTripAt(
  WidgetTester tester,
  FakeApi api, {
  KeyValueStore? store,
}) async {
  usePhoneScreen(tester);
  await pumpApp(
    tester,
    api: api,
    tokens: MemoryTokenStore(signedInTokens),
    store: store,
    extra: [
      clockProvider.overrideWithValue(() => now),
      locationReaderProvider.overrideWithValue(FakeLocation()),
    ],
  );
  await tester.tap(find.text('My trips'));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Trip details'));
  await tester.pumpAndSettle();
}

/// The pass screen redraws every second (its code counts down), so it never
/// "settles": pump a few frames instead.
Future<void> pumpFrames(WidgetTester tester) async {
  for (var i = 0; i < 5; i++) {
    await tester.pump(const Duration(milliseconds: 300));
  }
}

Future<void> tapButton(WidgetTester tester, String label) async {
  final button = find.text(label);
  await Scrollable.ensureVisible(tester.element(button), alignment: 0.5);
  await tester.pumpAndSettle();
  await tester.tap(button);
}

void main() {
  testWidgets('shows the pass as a QR code and a live six-digit code', (
    tester,
  ) async {
    final api = tripApi('confirmed', {
      'POST /api/v1/bookings/b1/attendance/pass/': (_) => ok(passJson()),
    });
    final store = MemoryKeyValueStore();
    await openTripAt(tester, api, store: store);

    await tapButton(tester, 'Show check-in pass');
    await pumpFrames(tester);

    expect(find.byType(CheckInPassScreen), findsOneWidget);
    expect(find.byType(QrImageView), findsOneWidget);
    expect(find.text('832 515'), findsOneWidget); // codeAt(secret, now)
    expect(find.textContaining('New code in'), findsOneWidget);
    final sent = api.requests.last.data as Map<String, Object?>;
    expect(sent['location'], {
      'latitude': '15.500000',
      'longitude': '73.800000',
      'accuracy_m': 12,
    });
    // Kept for when there's no signal.
    expect(await store.readJson('attendance.pass.b1'), isNotNull);
  });

  testWidgets('shows the saved pass when offline', (tester) async {
    final store = MemoryKeyValueStore();
    await store.writeJson('attendance.pass.b1', passJson());
    final api = tripApi('confirmed');
    await openTripAt(tester, api, store: store);
    await tapButton(tester, 'Show check-in pass');
    await pumpFrames(tester);

    expect(find.byType(QrImageView), findsOneWidget);
    expect(find.text('832 515'), findsOneWidget);
    // Still valid for over two hours: no network call needed.
    expect(
      api.calls,
      isNot(contains('POST /api/v1/bookings/b1/attendance/pass/')),
    );
  });

  testWidgets('logs hours, warning before the limits and refusing past them', (
    tester,
  ) async {
    var logged = <String, Object?>{};
    final api = tripApi('delivering', {
      'GET /api/v1/bookings/b1/hours/': (_) => ok({
        'week_start': '2026-11-30',
        'week_end': '2026-12-06',
        'logs': <Object?>[],
        'minutes': 0,
        'days_worked': 0,
        'weekly_cap_minutes': 1200,
        'hours_per_day': 4,
        'days_per_week': 5,
      }),
      'POST /api/v1/bookings/b1/hours/check/': (request) {
        final minutes = (request.data as Map)['minutes'] as int;
        return ok({
          'allowed': minutes <= 240,
          'problems': minutes > 240
              ? ['That makes 21 h this week; the agreed most is 20 h.']
              : <String>[],
          'warnings': ['That brings this week to 18 h of 20 h.'],
          'week_start': '2026-11-30',
          'week_minutes': minutes,
          'week_days': 1,
          'weekly_cap_minutes': 1200,
          'days_per_week': 5,
        });
      },
      'POST /api/v1/bookings/b1/hours/': (request) {
        logged = Map<String, Object?>.from(request.data as Map);
        return FakeResponse(201, {
          'log': {
            'id': 'h1',
            'day': '2026-12-01',
            'minutes': logged['minutes'],
            'note': '',
            'status': 'pending',
            'vendor_note': '',
            'reviewed_at': null,
            'created_at': '2026-12-01T10:00:00Z',
            'updated_at': '2026-12-01T10:00:00Z',
          },
          'check': {
            'allowed': true,
            'problems': <String>[],
            'warnings': <String>[],
            'week_start': '2026-11-30',
            'week_minutes': 120,
            'week_days': 1,
            'weekly_cap_minutes': 1200,
            'days_per_week': 5,
          },
        });
      },
    });
    await openTripAt(tester, api);
    await tapButton(tester, 'Log hours');
    await tester.pumpAndSettle();

    expect(find.text('0 h of 20 h this week'), findsOneWidget);
    await tester.tap(find.text('Tue 1 Dec'));
    await tester.pumpAndSettle();
    expect(find.text('2 h'), findsOneWidget);
    expect(find.text('That brings this week to 18 h of 20 h.'), findsOneWidget);

    // Past the agreed hours: refused before saving.
    for (var i = 0; i < 6; i++) {
      await tester.tap(find.byTooltip('More'));
      await tester.pump();
    }
    await tester.pumpAndSettle();
    expect(
      find.text('That makes 21 h this week; the agreed most is 20 h.'),
      findsOneWidget,
    );
    final save = find.widgetWithText(FilledButton, 'Save hours');
    expect(tester.widget<FilledButton>(save).onPressed, isNull);

    for (var i = 0; i < 6; i++) {
      await tester.tap(find.byTooltip('Less'));
      await tester.pump();
    }
    await tester.pumpAndSettle();
    await tester.tap(save);
    await tester.pumpAndSettle();
    expect(logged, {'day': '2026-12-01', 'minutes': 120, 'note': ''});
  });
}
