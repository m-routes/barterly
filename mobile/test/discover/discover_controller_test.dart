import 'package:barterly/src/api/token_store.dart';
import 'package:barterly/src/discover/discover_controller.dart';
import 'package:barterly/src/discover/discovery_filters.dart';
import 'package:barterly/src/pay_model.dart';
import 'package:barterly/src/platform/device_keys.dart';
import 'package:barterly/src/platform/key_value_store.dart';
import 'package:barterly/src/platform/network_status.dart';
import 'package:barterly/src/providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import '../fixtures.dart';
import '../helpers.dart';

ProviderContainer containerFor(
  FakeApi api, {
  KeyValueStore? store,
  NetworkStatus? network,
}) => ProviderContainer.test(
  retry: (_, _) => null,
  overrides: [
    ...testOverrides(
      api: api,
      tokens: MemoryTokenStore(signedInTokens),
      store: store,
      network: network,
    ),
    currentUserIdProvider.overrideWithValue('u1'),
  ],
);

/// Lets queued microtasks and fake HTTP calls finish.
Future<void> settle() async {
  for (var i = 0; i < 10; i++) {
    await Future<void>.delayed(Duration.zero);
  }
}

void main() {
  test('loads the first page and keeps a copy for offline', () async {
    final store = MemoryKeyValueStore();
    final api = FakeApi({
      'GET /api/v1/gigs/': (_) => ok(page([gigJson()], next: 'c2')),
    });
    final container = containerFor(api, store: store)
      ..listen(discoverProvider, (_, _) {});
    await settle();

    final state = container.read(discoverProvider);
    expect(state.loading, isFalse);
    expect([for (final g in state.gigs) g.id], ['g1']);
    expect(state.hasMore, isTrue);
    expect(state.offline, isFalse);
    expect(api.requests.single.queryParameters, {'sort': 'best_fit'});
    expect(store.data[DeviceKeys.discoverCache('u1')]?['params'], {
      'sort': 'best_fit',
    });
  });

  test('offline, it shows the saved page with when it was saved', () async {
    final store = MemoryKeyValueStore();
    await DiscoverCache(
      store,
      userId: 'u1',
      now: () => DateTime.utc(2026, 11, 13, 9),
    ).save(
      const DiscoveryFilters(payModels: {PayModel.barter}),
      // Cached pages never offer "load more".
      .fromJson(page([gigJson(id: 'cached')], next: 'c2')),
    );
    final network = FakeNetworkStatus(online: false);
    final api = FakeApi()..offline = true;
    final container = containerFor(api, store: store, network: network)
      ..listen(discoverProvider, (_, _) {});
    await settle();

    var state = container.read(discoverProvider);
    expect(state.offline, isTrue);
    expect(state.cachedAt, DateTime.utc(2026, 11, 13, 9).toLocal());
    expect(state.gigs.single.id, 'cached');
    expect(state.filters.payModels, {PayModel.barter});
    expect(state.hasMore, isFalse);

    // The network comes back: fresh results replace the copy.
    api
      ..offline = false
      ..routes['GET /api/v1/gigs/'] = (_) => ok(page([gigJson(id: 'fresh')]));
    network.online = true;
    await settle();
    state = container.read(discoverProvider);
    expect(state.offline, isFalse);
    expect(state.gigs.single.id, 'fresh');
    expect(
      api.requests.last.queryParameters['compensation_model'],
      'barter',
      reason: 'it reloads the filters the copy was saved with',
    );
  });

  test('offline with nothing saved is an error', () async {
    final api = FakeApi()..offline = true;
    final container = containerFor(api)..listen(discoverProvider, (_, _) {});
    await settle();
    final state = container.read(discoverProvider);
    expect(state.gigs, isEmpty);
    expect(state.error?.code, 'network_error');
  });

  test('load more passes the cursor and skips duplicates', () async {
    final api = FakeApi({
      'GET /api/v1/gigs/': (r) => r.queryParameters['cursor'] == 'c2'
          ? ok(page([gigJson(id: 'g2'), gigJson()]))
          : ok(page([gigJson()], next: 'c2')),
    });
    final container = containerFor(api)..listen(discoverProvider, (_, _) {});
    await settle();
    await container.read(discoverProvider.notifier).loadMore();

    final state = container.read(discoverProvider);
    expect([for (final g in state.gigs) g.id], ['g1', 'g2']);
    expect(state.hasMore, isFalse);
    expect(api.requests.last.queryParameters['cursor'], 'c2');
  });

  test('a filter change reloads with the new parameters', () async {
    final api = FakeApi();
    final container = containerFor(api)..listen(discoverProvider, (_, _) {});
    await settle();
    await container
        .read(discoverProvider.notifier)
        .setFilters(
          const DiscoveryFilters(
            payModels: {PayModel.paid},
            womenFriendly: true,
            sort: GigSort.newest,
          ),
        );
    expect(api.requests.last.queryParameters, {
      'compensation_model': 'paid',
      'women_friendly': true,
      'sort': 'newest',
    });
  });

  test('a slow old response does not overwrite a newer one', () async {
    var calls = 0;
    final api = FakeApi({
      'GET /api/v1/gigs/': (_) async {
        calls++;
        if (calls == 1) {
          await Future<void>.delayed(const Duration(milliseconds: 50));
          return ok(page([gigJson(id: 'old')]));
        }
        return ok(page([gigJson(id: 'new')]));
      },
    });
    final container = containerFor(api)..listen(discoverProvider, (_, _) {});
    await settle();
    await container
        .read(discoverProvider.notifier)
        .setFilters(const DiscoveryFilters(query: 'yoga'));
    await Future<void>.delayed(const Duration(milliseconds: 80));
    expect(container.read(discoverProvider).gigs.single.id, 'new');
  });
}
