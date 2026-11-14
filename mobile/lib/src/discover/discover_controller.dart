import 'dart:async';

import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/discover/discovery_filters.dart';
import 'package:barterly/src/discover/gig.dart';
import 'package:barterly/src/platform/device_keys.dart';
import 'package:barterly/src/platform/key_value_store.dart';
import 'package:barterly/src/providers.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show FutureProviderFamily;

/// The last first page of discover, kept so the feed still shows something
/// offline. One entry, replaced on every successful load.
class DiscoverCache {
  new(this._store, {required String userId, DateTime Function()? now})
    : key = DeviceKeys.discoverCache(userId),
      _now = now ?? DateTime.now;

  final String key;
  final KeyValueStore _store;
  final DateTime Function() _now;

  Future<void> save(DiscoveryFilters filters, GigPage page) =>
      _store.writeJson(key, {
        'saved_at': _now().toUtc().toIso8601String(),
        'params': filters.toParams(),
        'page': page.toJson(),
      });

  Future<CachedPage?> read() async {
    final json = await _store.readJson(key);
    if (json == null) return null;
    try {
      return (
        savedAt: DateTime.parse(json['saved_at']! as String).toLocal(),
        filters: DiscoveryFilters.fromParams(
          (json['params']! as Map).cast<String, Object?>(),
        ),
        page: GigPage.fromJson((json['page']! as Map).cast<String, Object?>()),
      );
    } on Object {
      // An entry from an older app version: ignore it.
      return null;
    }
  }
}

typedef CachedPage = ({
  DateTime savedAt,
  DiscoveryFilters filters,
  GigPage page,
});

@immutable
class DiscoverState {
  const new({
    this.filters = const DiscoveryFilters(),
    this.gigs = const [],
    this.nextCursor,
    this.loading = true,
    this.loadingMore = false,
    this.error,
    this.moreError,
    this.cachedAt,
  });

  final DiscoveryFilters filters;
  final List<Gig> gigs;
  final String? nextCursor;

  /// The first page is loading (or reloading after a filter change).
  final bool loading;
  final bool loadingMore;

  /// The last load failed. With [gigs] empty the screen shows an error.
  final ApiError? error;
  final ApiError? moreError;

  /// Set while showing the offline copy: when it was saved.
  final DateTime? cachedAt;

  bool get offline => cachedAt != null;
  bool get hasMore => nextCursor != null && !offline;

  DiscoverState copyWith({
    DiscoveryFilters? filters,
    List<Gig>? gigs,
    String? Function()? nextCursor,
    bool? loading,
    bool? loadingMore,
    ApiError? Function()? error,
    ApiError? Function()? moreError,
    DateTime? Function()? cachedAt,
  }) => DiscoverState(
    filters: filters ?? this.filters,
    gigs: gigs ?? this.gigs,
    nextCursor: nextCursor == null ? this.nextCursor : nextCursor(),
    loading: loading ?? this.loading,
    loadingMore: loadingMore ?? this.loadingMore,
    error: error == null ? this.error : error(),
    moreError: moreError == null ? this.moreError : moreError(),
    cachedAt: cachedAt == null ? this.cachedAt : cachedAt(),
  );
}

final discoverCacheProvider = Provider<DiscoverCache>(
  (ref) => DiscoverCache(
    ref.watch(keyValueStoreProvider),
    userId: ref.watch(currentUserIdProvider),
  ),
);

final discoverProvider = NotifierProvider<DiscoverController, DiscoverState>(
  DiscoverController.new,
);

class DiscoverController extends Notifier<DiscoverState> {
  /// Bumped on every first-page load, so a slow old response can't overwrite
  /// a newer one.
  int _generation = 0;

  @override
  DiscoverState build() {
    // Another account signed in: start over.
    ref.watch(currentUserIdProvider);
    // Back online while showing the offline copy: fetch fresh results.
    ref.listen(onlineProvider, (previous, next) {
      if (next.value == true && previous?.value != true && state.offline) {
        unawaited(refresh());
      }
    });
    unawaited(Future.microtask(refresh));
    return const DiscoverState();
  }

  Future<void> setFilters(DiscoveryFilters filters) async {
    if (filters == state.filters && !state.offline && state.error == null) {
      return;
    }
    state = state.copyWith(filters: filters);
    await refresh(showSkeleton: true);
  }

  /// Loads the first page again. Pull to refresh keeps the current results on
  /// screen; a filter change shows the skeleton instead.
  Future<void> refresh({bool showSkeleton = false}) async {
    final generation = ++_generation;
    final filters = state.filters;
    state = state.copyWith(
      loading: showSkeleton || state.gigs.isEmpty,
      gigs: showSkeleton ? const [] : null,
      error: () => null,
      moreError: () => null,
    );
    try {
      final page = await ref.read(gigsRepositoryProvider).discover(filters);
      if (!ref.mounted || generation != _generation) return;
      state = state.copyWith(
        gigs: page.gigs,
        nextCursor: () => page.nextCursor,
        loading: false,
        cachedAt: () => null,
      );
      await ref.read(discoverCacheProvider).save(filters, page);
    } on ApiError catch (error) {
      if (!ref.mounted || generation != _generation) return;
      if (error.code == 'network_error') {
        final cached = await ref.read(discoverCacheProvider).read();
        if (!ref.mounted || generation != _generation) return;
        if (cached != null) {
          state = state.copyWith(
            filters: cached.filters,
            gigs: cached.page.gigs,
            nextCursor: () => null,
            loading: false,
            cachedAt: () => cached.savedAt,
          );
          return;
        }
      }
      state = state.copyWith(loading: false, error: () => error);
    }
  }

  Future<void> loadMore() async {
    final cursor = state.nextCursor;
    if (cursor == null || state.loadingMore || state.loading || state.offline) {
      return;
    }
    final generation = _generation;
    state = state.copyWith(loadingMore: true, moreError: () => null);
    try {
      final page = await ref
          .read(gigsRepositoryProvider)
          .discover(state.filters, cursor: cursor);
      if (!ref.mounted || generation != _generation) return;
      final seen = {for (final g in state.gigs) g.id};
      state = state.copyWith(
        gigs: [...state.gigs, ...page.gigs.where((g) => !seen.contains(g.id))],
        nextCursor: () => page.nextCursor,
        loadingMore: false,
      );
    } on ApiError catch (error) {
      if (!ref.mounted || generation != _generation) return;
      state = state.copyWith(loadingMore: false, moreError: () => error);
    }
  }

  Gig? find(String id) => state.gigs.where((g) => g.id == id).firstOrNull;
}

/// One gig for the detail and apply screens: the discover card, plus the
/// detail when the API shares it. Works offline from the cached feed.
final FutureProviderFamily<Gig, String> gigProvider = FutureProvider.autoDispose
    .family<Gig, String>((ref, id) async {
      final repo = ref.watch(gigsRepositoryProvider);
      var card = ref.read(discoverProvider.notifier).find(id);
      if (card == null) {
        final cached = await ref.read(discoverCacheProvider).read();
        card = cached?.page.gigs.where((g) => g.id == id).firstOrNull;
      }
      if (card == null) {
        // Opened from a link: only the detail endpoint can help.
        return await guardApi(() async {
          final response = await ref
              .read(dioProvider)
              .get<Map<String, Object?>>('/api/v1/gigs/$id/');
          return Gig.fromJson(response.data!);
        });
      }
      try {
        return await repo.detail(card);
      } on ApiError catch (error) {
        if (error.code == 'network_error') return card;
        rethrow;
      }
    });
