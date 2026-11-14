import 'dart:typed_data';

import 'package:barterly/src/api/token_store.dart';
import 'package:barterly/src/config/env.dart';
import 'package:barterly/src/discover/discover_controller.dart';
import 'package:barterly/src/discover/discovery_filters.dart';
import 'package:barterly/src/discover/filter_sheet.dart';
import 'package:barterly/src/discover/gig.dart';
import 'package:barterly/src/discover/gig_map.dart';
import 'package:barterly/src/pay_model.dart';
import 'package:barterly/src/platform/key_value_store.dart';
import 'package:barterly/src/platform/network_status.dart';
import 'package:barterly/src/providers.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

import '../fixtures.dart';
import '../helpers.dart';

/// A 1x1 transparent PNG, so map tests never touch the network.
final _blankPng = Uint8List.fromList(const [
  0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00, 0x00, 0x0D, //
  0x49, 0x48, 0x44, 0x52, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
  0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4, 0x89, 0x00, 0x00, 0x00,
  0x0D, 0x49, 0x44, 0x41, 0x54, 0x78, 0x9C, 0x63, 0x00, 0x01, 0x00, 0x00,
  0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00, 0x00, 0x00, 0x00, 0x49,
  0x45, 0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82,
]);

class BlankTiles extends TileProvider {
  final List<TileCoordinates> asked = [];

  @override
  ImageProvider getImage(TileCoordinates coordinates, TileLayer options) {
    asked.add(coordinates);
    return MemoryImage(_blankPng);
  }
}

final Map<String, Object?> twoGigs = page([
  gigJson(),
  gigJson(
    id: 'g2',
    title: '3 reels and 5 stories for 4 nights',
    model: 'barter',
    property: 'Sea Salt Homestay',
    city: 'Palolem',
    lat: 15.01,
    lng: 74.02,
    fit: 86,
  ),
], next: 'c2');

Future<FakeApi> openDiscover(
  WidgetTester tester, {
  FakeApi? api,
  KeyValueStore? store,
  NetworkStatus? network,
  FakeUrlOpener? urls,
  BlankTiles? tiles,
}) async {
  usePhoneScreen(tester);
  final fake =
      api ??
      talentApi({
        'GET /api/v1/gigs/': (r) =>
            r.queryParameters['cursor'] == 'c2' ? ok(emptyPage) : ok(twoGigs),
      });
  await pumpApp(
    tester,
    api: fake,
    tokens: MemoryTokenStore(signedInTokens),
    store: store,
    network: network,
    urls: urls,
    extra: [mapTileProviderProvider.overrideWithValue(tiles ?? BlankTiles())],
  );
  return fake;
}

Map<String, dynamic> lastQuery(FakeApi api) =>
    api.requests.lastWhere((r) => r.path == '/api/v1/gigs/').queryParameters;

void main() {
  testWidgets('gigs show as cards ranked by fit', (tester) async {
    await openDiscover(tester);
    expect(find.text('Gigs for you'), findsOneWidget);
    expect(find.text('Kasol, Palolem'), findsOneWidget);
    expect(find.text('Ranked by fit with your profile'), findsOneWidget);
    expect(find.text('Reception and social media volunteer'), findsOneWidget);
    expect(find.text('92% fit'), findsOneWidget);
    expect(find.text('Pine Trail Hostel · Kasol'), findsOneWidget);
    expect(
      find.text('4 hrs/day · 5 days/week · Dorm bed + all meals'),
      findsWidgets,
    );
  });

  testWidgets('a pay chip filters, and All clears it', (tester) async {
    final api = await openDiscover(tester);
    await tester.tap(find.widgetWithText(ChoiceChip, 'Barter'));
    await tester.pumpAndSettle();
    expect(lastQuery(api)['compensation_model'], 'barter');

    await tester.tap(find.widgetWithText(ChoiceChip, 'All'));
    await tester.pumpAndSettle();
    expect(lastQuery(api).containsKey('compensation_model'), isFalse);
  });

  testWidgets('search sends keywords', (tester) async {
    final api = await openDiscover(tester);
    await tester.enterText(find.byType(TextField).first, 'yoga');
    await tester.testTextInput.receiveAction(TextInputAction.search);
    await tester.pumpAndSettle();
    expect(lastQuery(api)['q'], 'yoga');
  });

  testWidgets('the filter sheet sends its filters and shows a count', (
    tester,
  ) async {
    final api = await openDiscover(tester);
    await tester.tap(find.byTooltip('Filters'));
    await tester.pumpAndSettle();
    expect(find.byType(FilterSheet), findsOneWidget);
    expect(
      find.text('Nearest'),
      findsNothing,
      reason: 'distance needs a point first',
    );

    await tester.tap(find.widgetWithText(ChoiceChip, 'Newest'));
    await tester.tap(find.widgetWithText(FilterChip, 'Trip leader'));
    final sheetList = find
        .descendant(
          of: find.byType(FilterSheet),
          matching: find.byType(Scrollable),
        )
        .first;
    await tester.scrollUntilVisible(
      find.text('Verified hosts only'),
      200,
      scrollable: sheetList,
    );
    await tester.tap(find.text('Verified hosts only'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Show gigs'));
    await tester.pumpAndSettle();

    expect(lastQuery(api), {
      'role': 'trip_leader',
      'verified_hosts': true,
      'sort': 'newest',
    });
    expect(find.text('Newest first'), findsOneWidget);
    expect(find.byTooltip('Filters, 2 on'), findsOneWidget);
  });

  testWidgets('a search can be saved for alerts', (tester) async {
    final api = await openDiscover(
      tester,
      api: talentApi({
        'GET /api/v1/gigs/': (_) => ok(page([gigJson()])),
        'POST /api/v1/gigs/saved-searches/': (r) => FakeResponse(201, {
          'id': 's1',
          ...r.data! as Map<String, Object?>,
          'last_checked_at': null,
          'created_at': '2026-11-14T10:00:00Z',
        }),
      }),
    );
    await tester.tap(find.widgetWithText(ChoiceChip, 'Barter'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Filters'));
    await tester.pumpAndSettle();
    final sheetList = find
        .descendant(
          of: find.byType(FilterSheet),
          matching: find.byType(Scrollable),
        )
        .first;
    await tester.scrollUntilVisible(
      find.text('Save this search and get alerts'),
      200,
      scrollable: sheetList,
    );
    await tester.tap(find.text('Save this search and get alerts'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'Rishikesh yoga');
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();

    final post = api.requests.lastWhere((r) => r.method == 'POST');
    expect(post.data, {
      'name': 'Rishikesh yoga',
      'params': {
        'compensation_model': ['barter'],
        'sort': 'best_fit',
      },
      'alerts_enabled': true,
    });
    expect(
      find.text("Search saved. We'll tell you about new gigs."),
      findsOneWidget,
    );
  });

  testWidgets('no matches offers to clear the filters', (tester) async {
    final api = await openDiscover(
      tester,
      api: talentApi({
        'GET /api/v1/gigs/': (r) =>
            r.queryParameters.containsKey('q') ? ok(emptyPage) : ok(twoGigs),
      }),
    );
    await tester.enterText(find.byType(TextField).first, 'scuba');
    await tester.testTextInput.receiveAction(TextInputAction.search);
    await tester.pumpAndSettle();
    expect(find.text('No gigs match'), findsOneWidget);

    await tester.tap(find.text('Clear filters'));
    await tester.pumpAndSettle();
    expect(lastQuery(api), {'sort': 'best_fit'});
    expect(find.text('92% fit'), findsOneWidget);
  });

  testWidgets('a failed load explains and retries', (tester) async {
    final api = await openDiscover(
      tester,
      api: talentApi({
        'GET /api/v1/gigs/': (_) => apiError(500, 'server_error', 'Down.'),
      }),
    );
    expect(find.text("We couldn't load gigs"), findsOneWidget);
    api.routes['GET /api/v1/gigs/'] = (_) => ok(twoGigs);
    await tester.tap(find.text('Try again'));
    await tester.pumpAndSettle();
    expect(find.text('92% fit'), findsOneWidget);
  });

  testWidgets('skeleton cards show while the first page loads', (tester) async {
    usePhoneScreen(tester);
    final api = talentApi({
      'GET /api/v1/gigs/': (_) async {
        await Future<void>.delayed(const Duration(seconds: 1));
        return ok(twoGigs);
      },
    });
    await pumpApp(tester, api: api, tokens: MemoryTokenStore(signedInTokens));
    // pumpApp settled before the slow page arrived.
    expect(find.bySemanticsLabel('Loading gigs'), findsOneWidget);
    await tester.pump(const Duration(seconds: 1));
    await tester.pumpAndSettle();
    expect(find.text('92% fit'), findsOneWidget);
  });

  testWidgets('pull to refresh loads the first page again', (tester) async {
    final api = await openDiscover(tester);
    int firstPages() => api.requests
        .where(
          (r) =>
              r.path == '/api/v1/gigs/' &&
              !r.queryParameters.containsKey('cursor'),
        )
        .length;
    final before = firstPages();
    await tester.fling(find.text('92% fit'), const Offset(0, 400), 1000);
    await tester.pumpAndSettle();
    expect(firstPages(), before + 1);
  });

  testWidgets('scrolling to the end loads the next page', (tester) async {
    final api = await openDiscover(
      tester,
      api: talentApi({
        'GET /api/v1/gigs/': (r) => r.queryParameters['cursor'] == 'c2'
            ? ok(page([gigJson(id: 'g3', title: 'Morning yoga teacher')]))
            : ok(twoGigs),
      }),
    );
    await tester.drag(find.text('92% fit'), const Offset(0, -500));
    await tester.pumpAndSettle();
    expect(lastQuery(api)['cursor'], 'c2');
    await tester.scrollUntilVisible(
      find.text("That's every gig for now."),
      300,
      scrollable: find.byType(Scrollable).last,
    );
    expect(find.text('Morning yoga teacher'), findsOneWidget);
  });

  testWidgets('offline, the saved page shows under a banner', (tester) async {
    final store = MemoryKeyValueStore();
    await DiscoverCache(
      store,
      userId: talentJson['id']! as String,
      now: () => DateTime(2026, 11, 13, 9, 30),
    ).save(
      const DiscoveryFilters(payModels: {PayModel.volunteer}),
      GigPage.fromJson(page([gigJson()])),
    );
    final network = FakeNetworkStatus(online: false);
    // The account is known, but the feed request never gets a response.
    final api = talentApi({
      'GET /api/v1/gigs/': (_) => throw StateError('no network'),
    });
    await openDiscover(tester, api: api, store: store, network: network);

    expect(
      find.text("You're offline. Showing gigs saved 13 Nov at 09:30."),
      findsOneWidget,
    );
    expect(find.text('Reception and social media volunteer'), findsOneWidget);
    expect(find.text('Connect to see more gigs.'), findsOneWidget);
    // The saved page's filters are shown as they were.
    final volunteer = tester.widget<ChoiceChip>(
      find.widgetWithText(ChoiceChip, 'Volunteer'),
    );
    expect(volunteer.selected, isTrue);

    // Back online: the banner goes and fresh results load.
    api.routes['GET /api/v1/gigs/'] = (_) => ok(twoGigs);
    network.online = true;
    await tester.pumpAndSettle();
    expect(find.textContaining("You're offline"), findsNothing);
    expect(find.text('86% fit'), findsOneWidget);
  });

  testWidgets('offline with nothing saved says so', (tester) async {
    final api = talentApi()
      ..routes['GET /api/v1/gigs/'] = (r) => throw StateError('no network');
    await openDiscover(tester, api: api);
    expect(find.text("You're offline"), findsOneWidget);
  });

  group('map', () {
    testWidgets('shows OSM tiles with attribution that links to the '
        'copyright page', (tester) async {
      final urls = FakeUrlOpener();
      final tiles = BlankTiles();
      await openDiscover(tester, urls: urls, tiles: tiles);
      await tester.tap(find.byTooltip('Show map'));
      await tester.pumpAndSettle();

      final layer = tester.widget<TileLayer>(find.byType(TileLayer));
      expect(layer.urlTemplate, AppConfig.defaultMapTileUrl);
      expect(
        layer.tileProvider.headers['User-Agent'],
        contains(mapUserAgentPackage),
      );
      expect(tiles.asked, isNotEmpty);
      expect(
        find.text('Pins show the area, not the exact address.'),
        findsOneWidget,
      );

      await tester.tap(find.text('© OpenStreetMap contributors'));
      expect(urls.external, [
        Uri.parse('https://www.openstreetmap.org/copyright'),
      ]);
    });

    testWidgets('a pin opens a preview and then the gig', (tester) async {
      await openDiscover(
        tester,
        api: talentApi({
          'GET /api/v1/gigs/': (_) => ok(page([gigJson()])),
          'GET /api/v1/gigs/g1/public/': (_) =>
              apiError(403, 'permission_denied'),
        }),
      );
      await tester.tap(find.byTooltip('Show map'));
      await tester.pumpAndSettle();
      await tester.tap(
        find.bySemanticsLabel(RegExp('Reception and social media volunteer')),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('View gig'));
      await tester.pumpAndSettle();
      expect(find.text('Apply for this gig'), findsOneWidget);
    });

    testWidgets('gigs without a location are counted, not placed', (
      tester,
    ) async {
      await openDiscover(
        tester,
        api: talentApi({
          'GET /api/v1/gigs/': (_) =>
              ok(page([gigJson(), gigJson(id: 'g2', lat: null)])),
        }),
      );
      await tester.tap(find.byTooltip('Show map'));
      await tester.pumpAndSettle();
      expect(
        find.text(
          'Pins show the area, not the exact address. '
          '1 gig has no location.',
        ),
        findsOneWidget,
      );
    });
  });

  testWidgets('discover meets tap target and contrast guidelines', (
    tester,
  ) async {
    await openDiscover(tester);
    await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
    await expectLater(tester, meetsGuideline(textContrastGuideline));
  });
}
