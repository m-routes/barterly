import 'dart:async';

import 'package:barterly/src/agreements/offer_screen.dart';
import 'package:barterly/src/api/token_store.dart';
import 'package:barterly/src/notifications/push.dart';
import 'package:barterly/src/providers.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

import '../helpers.dart';
import 'agreements_test.dart' show offerJson, threadJson;

class FakePush implements PushMessaging {
  new({this.allowed = true, this.launched});

  final bool allowed;
  final OpenedPush? launched;
  final taps = StreamController<OpenedPush>.broadcast();
  final arrivals = StreamController<ReceivedPush>.broadcast();
  final refreshes = StreamController<String>.broadcast();
  bool deleted = false;

  @override
  Future<bool> requestPermission() async => allowed;

  @override
  Future<String?> token() async => 'fcm-token-1';

  @override
  Stream<String> get tokenRefreshes => refreshes.stream;

  @override
  Stream<OpenedPush> get opened => taps.stream;

  @override
  Stream<ReceivedPush> get received => arrivals.stream;

  @override
  Future<OpenedPush?> launchedFrom() async => launched;

  @override
  Future<void> deleteToken() async => deleted = true;

  @override
  String get platform => 'android';
}

Map<String, Object?> noteJson({
  String id = 'n1',
  bool read = false,
  String path = '/trips/offer/a1',
}) => {
  'id': id,
  'kind': 'application.offered',
  'title': 'You have an offer',
  'body': 'Front desk: answer within 48 hours.',
  'urgent': false,
  'app_path': path,
  'web_url': 'https://web.test/console/applicants/a1',
  'read': read,
  'read_at': null,
  'created_at': '2026-11-16T10:00:00Z',
};

Map<String, Object?> prefsJson({String locale = 'en'}) => {
  'locale': locale,
  'quiet_hours_enabled': true,
  'quiet_start': '22:00',
  'quiet_end': '08:00',
  'channels_available': ['in_app', 'push', 'email'],
  'event_types': [
    {
      'key': 'application.offered',
      'label': 'Offer sent to you',
      'urgent': false,
      'channels': {
        'in_app': {'enabled': true, 'locked': true},
        'push': {'enabled': true, 'locked': false},
        'email': {'enabled': true, 'locked': false},
      },
    },
  ],
};

FakeApi notifyApi() => talentApi({
  'POST /api/v1/notifications/devices/': (_) => const FakeResponse(204),
  'POST /api/v1/notifications/devices/remove/': (_) => const FakeResponse(204),
  'POST /api/v1/notifications/n1/read/': (_) => ok(noteJson(read: true)),
  'POST /api/v1/notifications/read-all/': (_) => ok({'marked': 1}),
  'GET /api/v1/notifications/': (_) => ok({
    'results': [noteJson(), noteJson(id: 'n2', read: true, path: '/trips')],
    'next': null,
  }),
  'GET /api/v1/notifications/preferences/': (_) => ok(prefsJson()),
  'PUT /api/v1/notifications/preferences/': (_) => ok(prefsJson(locale: 'hi')),
  'GET /api/v1/applications/a1/offers/': (_) => ok(
    threadJson([offerJson()], open: 'of1', yourTurn: true, canCounter: true),
  ),
  'POST /api/v1/auth/logout/': (_) => const FakeResponse(204),
});

Future<void> start(WidgetTester tester, FakeApi api, FakePush push) async {
  usePhoneScreen(tester);
  await pumpApp(
    tester,
    api: api,
    tokens: MemoryTokenStore(signedInTokens),
    extra: [pushMessagingProvider.overrideWithValue(push)],
  );
}

void main() {
  testWidgets('registers the device and opens a tapped push', (tester) async {
    final api = notifyApi();
    final push = FakePush();
    await start(tester, api, push);

    final registered = api.requests.singleWhere(
      (r) => r.path == '/api/v1/notifications/devices/',
    );
    expect(registered.data, {'token': 'fcm-token-1', 'platform': 'android'});

    push.taps.add(
      const OpenedPush(notificationId: 'n1', path: '/trips/offer/a1'),
    );
    await tester.pumpAndSettle();
    expect(find.byType(OfferScreen), findsOneWidget);
    final read = api.requests.singleWhere(
      (r) => r.path == '/api/v1/notifications/n1/read/',
    );
    expect(read.data, {'from_push': true});
  });

  testWidgets('a push that launched the app opens its screen', (tester) async {
    final api = notifyApi();
    await start(
      tester,
      api,
      FakePush(
        launched: const OpenedPush(
          notificationId: 'n1',
          path: '/trips/offer/a1',
        ),
      ),
    );
    expect(find.byType(OfferScreen), findsOneWidget);
  });

  testWidgets('no permission, no device registered', (tester) async {
    final api = notifyApi();
    await start(tester, api, FakePush(allowed: false));
    expect(api.calls, isNot(contains('POST /api/v1/notifications/devices/')));
  });

  test('a push without an app path is ignored', () {
    expect(OpenedPush.fromData({'path': 'https://x'}), isNull);
    expect(OpenedPush.fromData({}), isNull);
    expect(
      OpenedPush.fromData({'path': '/trips', 'notification_id': 'n'})?.path,
      '/trips',
    );
  });

  testWidgets('the inbox opens a notification and marks it read', (
    tester,
  ) async {
    final api = notifyApi();
    await start(tester, api, FakePush(allowed: false));
    await tester.tap(find.text('Profile'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Notifications'));
    await tester.pumpAndSettle();

    expect(find.text('Mark all 1 read'), findsOneWidget);
    await tester.tap(find.text('You have an offer').first);
    await tester.pumpAndSettle();
    expect(find.byType(OfferScreen), findsOneWidget);
    expect(api.calls, contains('POST /api/v1/notifications/n1/read/'));
  });

  testWidgets('settings change language and a channel', (tester) async {
    final api = notifyApi();
    await start(tester, api, FakePush(allowed: false));
    await tester.tap(find.text('Profile'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Notifications'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Notification settings'));
    await tester.pumpAndSettle();

    final inApp = tester.widget<FilterChip>(
      find.widgetWithText(FilterChip, 'In the app'),
    );
    expect(inApp.onSelected, isNull, reason: 'the inbox stays on');
    await tester.tap(find.text('हिन्दी'));
    await tester.tap(find.widgetWithText(FilterChip, 'Email'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Save settings'));
    await tester.tap(find.text('Save settings'));
    await tester.pumpAndSettle();

    final saved = api.requests.singleWhere((r) => r.method == 'PUT');
    expect(saved.data, {
      'locale': 'hi',
      'quiet_hours_enabled': true,
      'quiet_start': '22:00',
      'quiet_end': '08:00',
      'changes': [
        {
          'event_type': 'application.offered',
          'channel': 'email',
          'enabled': false,
        },
      ],
    });
    expect(find.text('Saved.'), findsOneWidget);
  });

  testWidgets('signing out removes the device first', (tester) async {
    final api = notifyApi();
    final push = FakePush();
    await start(tester, api, push);
    await tester.tap(find.text('Profile'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Sign out'));
    await tester.tap(find.text('Sign out'));
    // The device is removed before anything on screen changes.
    for (var i = 0; i < 5; i++) {
      await tester.pump(const Duration(milliseconds: 200));
    }
    await tester.pumpAndSettle();

    expect(find.text('Sign in to Barterly'), findsOneWidget);
    final removed = api.requests.singleWhere(
      (r) => r.path == '/api/v1/notifications/devices/remove/',
    );
    expect(removed.data, {'token': 'fcm-token-1'});
    expect(push.deleted, isTrue);
  });

  testWidgets('a push while the app is open shows a banner that opens it', (
    tester,
  ) async {
    final api = notifyApi();
    final push = FakePush();
    await start(tester, api, push);

    push.arrivals.add(
      const ReceivedPush(
        title: 'You have an offer',
        body: 'Front desk: answer within 48 hours.',
        open: OpenedPush(notificationId: 'n1', path: '/trips/offer/a1'),
      ),
    );
    await tester.pumpAndSettle(); // the banner slides in
    expect(
      find.text('You have an offer\nFront desk: answer within 48 hours.'),
      findsOneWidget,
    );
    await tester.tap(find.widgetWithText(SnackBarAction, 'Open'));
    await tester.pumpAndSettle();
    expect(find.byType(OfferScreen), findsOneWidget);
    final read = api.requests.singleWhere(
      (r) => r.path == '/api/v1/notifications/n1/read/',
    );
    expect(read.data, {'from_push': true});
  });

  testWidgets('a push without a screen to open still shows', (tester) async {
    final api = notifyApi();
    final push = FakePush();
    await start(tester, api, push);
    push.arrivals.add(const ReceivedPush(title: 'Hello', body: 'Welcome'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Hello\nWelcome'), findsOneWidget);
    expect(find.text('Open'), findsNothing);
  });
}
