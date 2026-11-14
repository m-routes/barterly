import 'dart:async';

import 'package:barterly/src/discover/discover_controller.dart';
import 'package:barterly/src/discover/discovery_filters.dart';
import 'package:barterly/src/discover/filter_sheet.dart';
import 'package:barterly/src/discover/gig.dart';
import 'package:barterly/src/discover/gig_card.dart';
import 'package:barterly/src/discover/gig_map.dart';
import 'package:barterly/src/pay_model.dart';
import 'package:barterly/src/theme/tokens.dart';
import 'package:barterly/src/widgets/feedback.dart';
import 'package:barterly/src/widgets/states.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

/// The Discover tab (design canvas: Main).
class DiscoverScreen extends ConsumerStatefulWidget {
  const new({super.key});

  @override
  ConsumerState<DiscoverScreen> createState() => _DiscoverScreenState();
}

class _DiscoverScreenState extends ConsumerState<DiscoverScreen> {
  final _search = TextEditingController();
  bool _map = false;

  @override
  void initState() {
    super.initState();
    _search.text = ref.read(discoverProvider).filters.query;
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  DiscoverController get _controller => ref.read(discoverProvider.notifier);

  void _apply(DiscoveryFilters filters) {
    if (_search.text != filters.query) _search.text = filters.query;
    unawaited(_controller.setFilters(filters));
  }

  void _open(Gig gig) => unawaited(context.push('/discover/gig/${gig.id}'));

  Future<void> _openFilters(DiscoveryFilters current) async {
    final next = await showFilterSheet(context, current);
    if (next != null) _apply(next);
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(discoverProvider);
    final filters = state.filters;
    final theme = Theme.of(context);
    final cities = {
      for (final g in state.gigs.take(6))
        if (g.property.city.isNotEmpty) g.property.city,
    }.take(3);
    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 20, 12, 0),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          cities.isEmpty
                              ? 'Work-exchange stays in India'
                              : cities.join(', '),
                          style: const TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w500,
                            color: BarterlyColors.inkMuted,
                          ),
                        ),
                        Semantics(
                          header: true,
                          child: Text(
                            'Gigs for you',
                            style: theme.textTheme.headlineMedium?.copyWith(
                              fontSize: 28,
                              height: 1.1,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  IconButton.outlined(
                    tooltip: _map ? 'Show list' : 'Show map',
                    style: IconButton.styleFrom(
                      side: const BorderSide(color: BarterlyColors.border),
                      backgroundColor: BarterlyColors.surface,
                    ),
                    onPressed: () => setState(() => _map = !_map),
                    icon: Icon(
                      _map ? Icons.view_agenda_outlined : Icons.map_outlined,
                    ),
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 0),
              child: Row(
                spacing: 10,
                children: [
                  Expanded(
                    child: TextField(
                      controller: _search,
                      textInputAction: TextInputAction.search,
                      onSubmitted: (q) => _apply(filters.copyWith(query: q)),
                      decoration: InputDecoration(
                        hintText: 'Role, skill or place',
                        prefixIcon: const Icon(Icons.search),
                        suffixIcon: ListenableBuilder(
                          listenable: _search,
                          builder: (_, _) => _search.text.isEmpty
                              ? const SizedBox.shrink()
                              : IconButton(
                                  tooltip: 'Clear search',
                                  icon: const Icon(Icons.close),
                                  onPressed: () {
                                    _search.clear();
                                    _apply(filters.copyWith(query: ''));
                                  },
                                ),
                        ),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide: const BorderSide(
                            color: BarterlyColors.fieldBorder,
                          ),
                        ),
                        focusedBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide: const BorderSide(
                            color: BarterlyColors.accent,
                            width: 2,
                          ),
                        ),
                      ),
                    ),
                  ),
                  Badge(
                    isLabelVisible: filters.sheetCount > 0,
                    label: Text('${filters.sheetCount}'),
                    child: IconButton.filled(
                      tooltip: filters.sheetCount == 0
                          ? 'Filters'
                          : 'Filters, ${filters.sheetCount} on',
                      style: IconButton.styleFrom(
                        minimumSize: const Size(48, 48),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(14),
                        ),
                      ),
                      onPressed: () => _openFilters(filters),
                      icon: const Icon(Icons.tune),
                    ),
                  ),
                ],
              ),
            ),
            _PayModelChips(
              selected: filters.payModels,
              onChanged: (models) =>
                  _apply(filters.copyWith(payModels: models)),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 4, 20, 4),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      filters.sort.caption,
                      style: const TextStyle(
                        fontSize: 13,
                        color: BarterlyColors.inkMuted,
                      ),
                    ),
                  ),
                  FilterChip(
                    avatar: const Icon(Icons.shield_outlined, size: 16),
                    showCheckmark: false,
                    label: const Text('Women-friendly'),
                    selected: filters.womenFriendly,
                    onSelected: (on) =>
                        _apply(filters.copyWith(womenFriendly: on)),
                  ),
                ],
              ),
            ),
            if (state.cachedAt case final savedAt?)
              OfflineBanner(
                message:
                    "You're offline. Showing gigs saved "
                    '${savedAtLabel(savedAt)}.',
                onRetry: () => unawaited(_controller.refresh()),
              ),
            Expanded(
              child: _map
                  ? _MapBody(state: state, onOpen: _open, onApply: _apply)
                  : _ListBody(
                      state: state,
                      onOpen: _open,
                      onClear: () {
                        _search.clear();
                        _apply(const DiscoveryFilters());
                      },
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PayModelChips extends StatelessWidget {
  const new({required this.selected, required this.onChanged});

  final Set<PayModel> selected;
  final void Function(Set<PayModel>) onChanged;

  @override
  Widget build(BuildContext context) {
    Widget chip(String label, {required bool on, required VoidCallback tap}) =>
        Padding(
          padding: const EdgeInsets.only(right: 8),
          child: ChoiceChip(
            label: Text(label),
            selected: on,
            showCheckmark: false,
            onSelected: (_) => tap(),
            selectedColor: BarterlyColors.accent,
            labelStyle: TextStyle(
              color: on ? BarterlyColors.onAccent : BarterlyColors.ink,
              fontWeight: on ? FontWeight.w600 : FontWeight.w500,
            ),
            backgroundColor: BarterlyColors.surface,
            side: BorderSide(
              color: on ? BarterlyColors.accent : BarterlyColors.chipBorder,
            ),
            shape: const StadiumBorder(),
          ),
        );
    return SizedBox(
      height: 60,
      child: ListView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.fromLTRB(20, 10, 12, 0),
        children: [
          chip('All', on: selected.isEmpty, tap: () => onChanged(const {})),
          for (final model in PayModel.values)
            chip(
              model.label,
              on: selected.contains(model),
              tap: () => onChanged(
                selected.contains(model)
                    ? ({...selected}..remove(model))
                    : {...selected, model},
              ),
            ),
        ],
      ),
    );
  }
}

/// Fills the space and still allows pull to refresh (for empty and error
/// states).
class _Fill extends StatelessWidget {
  const new({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) => CustomScrollView(
    physics: const AlwaysScrollableScrollPhysics(),
    slivers: [SliverFillRemaining(hasScrollBody: false, child: child)],
  );
}

class _ListBody extends ConsumerWidget {
  const new({required this.state, required this.onOpen, required this.onClear});

  final DiscoverState state;
  final void Function(Gig) onOpen;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final controller = ref.read(discoverProvider.notifier);
    final Widget body;
    if (state.loading && state.gigs.isEmpty) {
      body = const SkeletonList(label: 'Loading gigs');
    } else if (state.error case final error? when state.gigs.isEmpty) {
      body = _Fill(
        child: ErrorView(
          title: error.code == 'network_error'
              ? "You're offline"
              : "We couldn't load gigs",
          message: error.code == 'network_error'
              ? 'Connect to the internet to see gigs. Gigs you have seen '
                    'before will show here once you have loaded them once.'
              : error.userMessage,
          onRetry: () => unawaited(controller.refresh()),
        ),
      );
    } else if (state.gigs.isEmpty) {
      final filtered = !state.filters.isEmpty;
      body = _Fill(
        child: EmptyState(
          icon: Icons.travel_explore_outlined,
          title: filtered ? 'No gigs match' : 'No gigs right now',
          message: filtered
              ? 'Try fewer filters, other dates or another place.'
              : 'New gigs are added every week. Pull down to check again.',
          action: filtered
              ? OutlinedButton(
                  onPressed: onClear,
                  child: const Text('Clear filters'),
                )
              : null,
        ),
      );
    } else {
      body = NotificationListener<ScrollNotification>(
        onNotification: (n) {
          if (n.metrics.extentAfter < 600) unawaited(controller.loadMore());
          return false;
        },
        child: ListView.separated(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
          itemCount: state.gigs.length + 1,
          separatorBuilder: (_, _) => const SizedBox(height: 14),
          itemBuilder: (context, i) {
            if (i < state.gigs.length) {
              final gig = state.gigs[i];
              return GigCard(gig: gig, onTap: () => onOpen(gig));
            }
            return _ListFooter(state: state, onRetry: controller.loadMore);
          },
        ),
      );
    }
    return RefreshIndicator(onRefresh: controller.refresh, child: body);
  }
}

class _ListFooter extends StatelessWidget {
  const new({required this.state, required this.onRetry});

  final DiscoverState state;
  final Future<void> Function() onRetry;

  @override
  Widget build(BuildContext context) {
    if (state.loadingMore) {
      return const Padding(
        padding: EdgeInsets.all(16),
        child: Center(child: CircularProgressIndicator()),
      );
    }
    if (state.moreError case final error?) {
      return Column(
        children: [
          Text(
            error.code == 'network_error'
                ? "Couldn't load more. You seem to be offline."
                : "Couldn't load more gigs.",
            style: const TextStyle(color: BarterlyColors.inkMuted),
          ),
          TextButton(
            onPressed: () => unawaited(onRetry()),
            child: const Text('Try again'),
          ),
        ],
      );
    }
    if (state.hasMore) return const SizedBox(height: 48);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Text(
        state.offline
            ? 'Connect to see more gigs.'
            : "That's every gig for now.",
        textAlign: TextAlign.center,
        style: const TextStyle(color: BarterlyColors.inkMuted),
      ),
    );
  }
}

class _MapBody extends StatelessWidget {
  const new({required this.state, required this.onOpen, required this.onApply});

  final DiscoverState state;
  final void Function(Gig) onOpen;
  final void Function(DiscoveryFilters) onApply;

  @override
  Widget build(BuildContext context) {
    if (state.loading && state.gigs.isEmpty) {
      return const LoadingView(label: 'Loading gigs…');
    }
    if (state.error case final error? when state.gigs.isEmpty) {
      return ErrorView(
        title: "We couldn't load gigs",
        message: error.userMessage,
      );
    }
    return GigMap(
      gigs: state.gigs,
      onOpen: onOpen,
      onSearchArea: (point, radiusKm) => onApply(
        state.filters.copyWith(
          point: () => point,
          radiusKm: () => radiusKm,
          sort: GigSort.distance,
        ),
      ),
    );
  }
}
