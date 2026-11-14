import 'package:barterly/src/api/token_store.dart';
import 'package:barterly/src/apply/apply_screen.dart';
import 'package:barterly/src/discover/gig_detail_screen.dart';
import 'package:barterly/src/platform/device_keys.dart';
import 'package:barterly/src/platform/key_value_store.dart';
import 'package:barterly/src/platform/media_picker.dart';
import 'package:barterly/src/platform/network_status.dart';
import 'package:barterly/src/profile/talent_profile.dart' show formatDate;
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

import '../fixtures.dart';
import '../helpers.dart';

const question = 'Can you commit to the full dates?';

/// The talent API with one gig. The gig detail answers with screening
/// questions when [detail] is true, or 403 like the current backend.
FakeApi gigApi({bool detail = true, Handler? onApply}) {
  var applied = false;
  return talentApi({
    'GET /api/v1/gigs/': (_) => ok(page([gigJson()])),
    'GET /api/v1/gigs/g1/public/': (_) => detail
        ? ok({
            'id': 'g1',
            'property': 'p-g1',
            'description': 'Welcome guests and handle check-in at the desk',
            'screening_questions': [question],
          })
        : apiError(403, 'permission_denied', 'Vendors only.'),
    'GET /api/v1/applications/mine/': (_) =>
        ok([if (applied) applicationJson(attachments: 2)]),
    'POST /api/v1/media/upload-url/': (_) =>
        FakeResponse(201, uploadTicket('m1')),
    'PUT https://storage.test/upload/m1': (_) => const FakeResponse(200),
    'POST /api/v1/media/confirm/': (_) => ok({'id': 'm1'}),
    'POST /api/v1/gigs/g1/applications/':
        onApply ??
        (_) {
          applied = true;
          return FakeResponse(201, applicationJson(attachments: 2));
        },
  });
}

Finder get formList => find
    .descendant(of: find.byType(ApplyForm), matching: find.byType(Scrollable))
    .first;

Future<void> scrollTo(WidgetTester tester, Finder finder) =>
    tester.scrollUntilVisible(finder, 200, scrollable: formList);

Future<void> openApply(
  WidgetTester tester,
  FakeApi api, {
  FakeMediaPicker? picker,
  NetworkStatus? network,
  KeyValueStore? store,
}) async {
  usePhoneScreen(tester);
  await pumpApp(
    tester,
    api: api,
    tokens: MemoryTokenStore(signedInTokens),
    picker: picker,
    network: network,
    store: store,
  );
  await tester.tap(find.text('Reception and social media volunteer'));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Apply for this gig'));
  await tester.pumpAndSettle();
  expect(find.byType(ApplyForm), findsOneWidget);
}

Future<void> fillForm(WidgetTester tester, {bool answer = true}) async {
  await tester.enterText(
    find.widgetWithText(TextFormField, 'Your pitch'),
    'I ran the front desk at a Manali hostel for a season.',
  );
  if (answer) {
    await scrollTo(tester, find.widgetWithText(TextFormField, question));
    await tester.enterText(find.widgetWithText(TextFormField, question), 'Yes');
  }
  await scrollTo(tester, find.text(agreementText));
  await tester.tap(find.byType(Checkbox));
  await tester.pump();
}

Future<void> send(WidgetTester tester) async {
  await tester.tap(find.text('Send application'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('gig detail shows the terms, fit and safety note', (
    tester,
  ) async {
    usePhoneScreen(tester);
    await pumpApp(
      tester,
      api: gigApi(),
      tokens: MemoryTokenStore(signedInTokens),
    );
    await tester.tap(find.text('Reception and social media volunteer'));
    await tester.pumpAndSettle();

    expect(
      find.text('Pine Trail Hostel · Kasol, Himachal Pradesh'),
      findsOneWidget,
    );
    expect(find.text('ID verified host'), findsOneWidget);
    expect(find.text('Women-friendly host'), findsOneWidget);
    expect(find.text('4 hrs/day · 5 days/week'), findsOneWidget);
    expect(find.text('Dorm bed + all meals'), findsOneWidget);
    expect(
      find.text('Welcome guests and handle check-in at the desk'),
      findsOneWidget,
    );
    expect(find.text('Speaks English or Hindi'), findsOneWidget);
    final detailList = find
        .descendant(
          of: find.byType(GigDetailScreen),
          matching: find.byType(Scrollable),
        )
        .first;
    await tester.scrollUntilVisible(
      find.text('Why this is a 92% fit'),
      200,
      scrollable: detailList,
    );
    await tester.ensureVisible(find.text('Why this is a 92% fit'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Why this is a 92% fit'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('No past gigs yet. (no data yet)'));
    expect(find.text('No past gigs yet. (no data yet)'), findsOneWidget);
    expect(find.textContaining('Host contact details unlock'), findsOneWidget);
  });

  testWidgets('the pitch and the agreement are required', (tester) async {
    final api = gigApi();
    await openApply(tester, api);
    await send(tester);

    await scrollTo(tester, find.text('Tell the host why you’re a good fit.'));
    expect(find.text('Tell the host why you’re a good fit.'), findsOneWidget);
    await scrollTo(tester, find.text('Answer this question.'));
    expect(find.text('Answer this question.'), findsOneWidget);
    await scrollTo(tester, find.text('Tick this to send your application.'));
    expect(find.text('Tick this to send your application.'), findsOneWidget);
    expect(api.calls.where((c) => c.startsWith('POST')), isEmpty);
  });

  testWidgets('the agreement alone blocks sending', (tester) async {
    final api = gigApi();
    await openApply(tester, api);
    await fillForm(tester);
    // Untick it again.
    await tester.tap(find.byType(Checkbox));
    await send(tester);
    expect(find.text('Tick this to send your application.'), findsOneWidget);
    expect(api.calls.where((c) => c.startsWith('POST')), isEmpty);
  });

  testWidgets('sends pitch, dates, answers, a photo and a link', (
    tester,
  ) async {
    final picker = FakeMediaPicker()..addPhoto('mural.jpg');
    final api = gigApi();
    await openApply(tester, api, picker: picker);
    await fillForm(tester);

    // A photo from the gallery.
    await scrollTo(tester, find.text('Photos'));
    await tester.tap(find.text('Photos'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Choose from gallery'));
    await tester.pumpAndSettle();
    expect(find.text('mural.jpg'), findsOneWidget);

    // A link, after an http one is refused.
    await tester.tap(find.text('Doc or link'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Add a link'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Link'),
      'http://example.com/reel',
    );
    await tester.tap(find.text('Add'));
    await tester.pumpAndSettle();
    expect(find.text('Use an https:// link.'), findsOneWidget);
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Link'),
      'https://example.com/reel',
    );
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Title (optional)'),
      'Showreel',
    );
    await tester.tap(find.text('Add'));
    await tester.pumpAndSettle();
    expect(find.text('Showreel'), findsOneWidget);

    await send(tester);

    expect(
      api.calls.where((c) => c.startsWith('POST') || c.startsWith('PUT')),
      [
        'POST /api/v1/media/upload-url/',
        'PUT https://storage.test/upload/m1',
        'POST /api/v1/media/confirm/',
        'POST /api/v1/gigs/g1/applications/',
      ],
    );
    final body = api.requests.lastWhere((r) => r.method == 'POST').data as Map;
    expect(
      body['pitch'],
      'I ran the front desk at a Manali hostel for a season.',
    );
    expect(body['answers'], ['Yes']);
    // Defaults: the gig's start, for its 14-day minimum stay.
    expect(body['proposed_start'], formatDate(gigStart));
    expect(
      body['proposed_end'],
      formatDate(gigStart.add(const Duration(days: 14))),
    );
    expect(body['attachments'], [
      {'kind': 'photo', 'media_id': 'm1', 'title': 'mural.jpg'},
      {'kind': 'link', 'url': 'https://example.com/reel', 'title': 'Showreel'},
    ]);
    expect(picker.sources, [PickSource.gallery]);
    expect(picker.discarded, ['/kept/mural.jpg']);

    // Back on the gig: sent, and the button says so.
    expect(find.textContaining('Application sent.'), findsOneWidget);
    expect(find.text('You applied'), findsOneWidget);
  });

  testWidgets('every reason the API refuses is listed', (tester) async {
    final api = gigApi(
      onApply: (_) => apiError(
        422,
        'application_blocked',
        "You can't apply to this gig yet.",
        {
          'reasons': [
            {
              'code': 'verification_required',
              'message': 'This gig needs a verified ID.',
            },
            {
              'code': 'stay_too_short',
              'message': 'This gig needs a stay of at least 14 days.',
            },
          ],
        },
      ),
    );
    await openApply(tester, api);
    await fillForm(tester);
    await send(tester);

    expect(find.text("You can't apply yet"), findsOneWidget);
    expect(find.text('• This gig needs a verified ID.'), findsOneWidget);
    expect(
      find.text('• This gig needs a stay of at least 14 days.'),
      findsOneWidget,
    );
    // Still on the form, nothing lost.
    expect(find.byType(ApplyForm), findsOneWidget);
  });

  testWidgets('without the gig detail, it still applies (no questions)', (
    tester,
  ) async {
    final api = gigApi(detail: false);
    await openApply(tester, api);
    expect(find.text('Questions from the host'), findsNothing);
    await fillForm(tester, answer: false);
    await send(tester);
    final body = api.requests.lastWhere((r) => r.method == 'POST').data as Map;
    expect(body['answers'], isEmpty);
    expect(find.textContaining('Application sent.'), findsOneWidget);
  });

  testWidgets('offline, the application is queued and sent later', (
    tester,
  ) async {
    final network = FakeNetworkStatus();
    final store = MemoryKeyValueStore();
    final picker = FakeMediaPicker()..addPhoto('mural.jpg');
    final api = gigApi();
    await openApply(
      tester,
      api,
      network: network,
      store: store,
      picker: picker,
    );
    await fillForm(tester);
    await scrollTo(tester, find.text('Photos'));
    await tester.tap(find.text('Photos'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Take a photo'));
    await tester.pumpAndSettle();

    network.online = false;
    await send(tester);

    expect(find.textContaining('saved and will send'), findsOneWidget);
    expect(find.text('Waiting to send'), findsOneWidget);
    expect(api.calls.where((c) => c.startsWith('POST')), isEmpty);
    expect(
      store.data[DeviceKeys.outbox(talentJson['id']! as String)]?['drafts'],
      hasLength(1),
    );

    // The snackbar's shortcut to My trips.
    await tester.tap(find.widgetWithText(SnackBarAction, 'My trips'));
    await tester.pumpAndSettle();
    expect(find.text('Waiting for network'), findsOneWidget);
    expect(find.text('Reception and social media volunteer'), findsOneWidget);

    network.online = true;
    await tester.pumpAndSettle();

    expect(api.calls.where((c) => c.startsWith('POST')), [
      'POST /api/v1/media/upload-url/',
      'POST /api/v1/media/confirm/',
      'POST /api/v1/gigs/g1/applications/',
    ]);
    expect(find.text('Waiting for network'), findsNothing);
    expect(find.text('Applied'), findsOneWidget);
    expect(
      store.data[DeviceKeys.outbox(talentJson['id']! as String)]?['drafts'],
      isEmpty,
    );
  });

  testWidgets('My trips lists applications and withdraws one', (tester) async {
    var status = 'applied';
    final api = talentApi({
      'GET /api/v1/applications/mine/': (_) =>
          ok([applicationJson(status: status)]),
      'POST /api/v1/applications/a1/withdraw/': (_) {
        status = 'withdrawn';
        return ok(applicationJson(status: status));
      },
    });
    usePhoneScreen(tester);
    await pumpApp(tester, api: api, tokens: MemoryTokenStore(signedInTokens));
    await tester.tap(find.text('My trips'));
    await tester.pumpAndSettle();
    expect(find.text('Applied'), findsOneWidget);
    expect(find.text('12 Dec to 26 Dec'), findsOneWidget);

    await tester.tap(find.text('Withdraw'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Withdraw'));
    await tester.pumpAndSettle();

    expect(api.requests.last.path, '/api/v1/applications/mine/');
    expect(find.text('Withdrawn'), findsOneWidget);
    expect(find.text('Withdraw'), findsNothing);
  });

  testWidgets('My trips offline shows a retry', (tester) async {
    final api = talentApi({
      'GET /api/v1/applications/mine/': (_) => throw StateError('offline'),
    });
    usePhoneScreen(tester);
    await pumpApp(tester, api: api, tokens: MemoryTokenStore(signedInTokens));
    await tester.tap(find.text('My trips'));
    await tester.pumpAndSettle();
    expect(find.text("You're offline"), findsOneWidget);
    expect(find.text('Try again'), findsOneWidget);
  });
}
