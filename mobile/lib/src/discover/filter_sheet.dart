import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/discover/discovery_filters.dart';
import 'package:barterly/src/discover/gig.dart';
import 'package:barterly/src/discover/gigs_repository.dart';
import 'package:barterly/src/providers.dart';
import 'package:barterly/src/theme/tokens.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

final FutureProvider<List<SavedSearch>> savedSearchesProvider =
    FutureProvider.autoDispose<List<SavedSearch>>(
      (ref) => ref.watch(gigsRepositoryProvider).savedSearches(),
    );

/// Opens the filter sheet; returns the new filters, or null if dismissed.
Future<DiscoveryFilters?> showFilterSheet(
  BuildContext context,
  DiscoveryFilters current,
) => showModalBottomSheet<DiscoveryFilters>(
  context: context,
  isScrollControlled: true,
  useSafeArea: true,
  showDragHandle: true,
  backgroundColor: BarterlyColors.ground,
  builder: (_) => FilterSheet(initial: current),
);

const _stayOptions = [7, 14, 30, 60];

class FilterSheet extends ConsumerStatefulWidget {
  const new({required this.initial, super.key});

  final DiscoveryFilters initial;

  @override
  ConsumerState<FilterSheet> createState() => _FilterSheetState();
}

class _FilterSheetState extends ConsumerState<FilterSheet> {
  late DiscoveryFilters _filters = widget.initial;
  late final _city = TextEditingController(text: widget.initial.city);

  @override
  void dispose() {
    _city.dispose();
    super.dispose();
  }

  /// Changes the latest filters (not the ones from the last build, so quick
  /// taps don't undo each other).
  void _update(DiscoveryFilters Function(DiscoveryFilters f) change) =>
      setState(() => _filters = change(_filters));

  DiscoveryFilters get _result => _filters.copyWith(city: _city.text);

  Future<void> _pickDates() async {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final range = await showDateRangePicker(
      context: context,
      firstDate: today,
      lastDate: today.add(const Duration(days: 365)),
      initialDateRange: _filters.startFrom != null && _filters.startTo != null
          ? DateTimeRange(start: _filters.startFrom!, end: _filters.startTo!)
          : null,
      helpText: 'Gigs starting between',
    );
    if (range == null) return;
    _update(
      (f) => f.copyWith(startFrom: () => range.start, startTo: () => range.end),
    );
  }

  Future<void> _saveSearch() async {
    final name = await showDialog<String>(
      context: context,
      builder: (_) => const _NameDialog(),
    );
    if (name == null || name.trim().isEmpty || !mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref.read(gigsRepositoryProvider).saveSearch(name.trim(), _result);
      ref.invalidate(savedSearchesProvider);
      messenger.showSnackBar(
        const SnackBar(
          content: Text("Search saved. We'll tell you about new gigs."),
        ),
      );
    } on ApiError catch (error) {
      messenger.showSnackBar(
        SnackBar(
          content: Text(
            error.isValidation && error.fieldErrors.isNotEmpty
                ? error.fieldErrors.values.first
                : error.userMessage,
          ),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final f = _filters;
    Widget heading(String text) => Padding(
      padding: const EdgeInsets.only(top: 20, bottom: 8),
      child: Semantics(
        header: true,
        child: Text(text, style: theme.textTheme.titleMedium),
      ),
    );
    final sorts = [
      for (final s in GigSort.values)
        if (s != GigSort.distance || f.point != null) s,
    ];
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20),
          child: Row(
            children: [
              Expanded(
                child: Text('Filters', style: theme.textTheme.titleLarge),
              ),
              TextButton(
                onPressed: () {
                  _city.clear();
                  _update((f) => f.clearSheet());
                },
                child: const Text('Clear'),
              ),
            ],
          ),
        ),
        Flexible(
          child: ListView(
            shrinkWrap: true,
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
            children: [
              const _SavedSearches(),
              heading('Sort by'),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final s in sorts)
                    ChoiceChip(
                      label: Text(s.label),
                      selected: f.sort == s,
                      onSelected: (_) => _update((f) => f.copyWith(sort: s)),
                    ),
                ],
              ),
              heading('Role'),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final r in RoleTemplate.values)
                    FilterChip(
                      label: Text(r.label),
                      selected: f.roles.contains(r),
                      onSelected: (on) => _update(
                        (f) => f.copyWith(
                          roles: on
                              ? {...f.roles, r}
                              : ({...f.roles}..remove(r)),
                        ),
                      ),
                    ),
                ],
              ),
              heading('Stay'),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final s in StayType.values)
                    FilterChip(
                      label: Text(s.label),
                      selected: f.stayTypes.contains(s),
                      onSelected: (on) => _update(
                        (f) => f.copyWith(
                          stayTypes: on
                              ? {...f.stayTypes, s}
                              : ({...f.stayTypes}..remove(s)),
                        ),
                      ),
                    ),
                ],
              ),
              heading('Where'),
              TextField(
                controller: _city,
                textInputAction: TextInputAction.done,
                decoration: const InputDecoration(
                  labelText: 'City',
                  hintText: 'Kasol, Goa, Rishikesh…',
                ),
              ),
              if (f.point != null)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.map_outlined),
                  title: Text(
                    'Within ${f.radiusKm?.round() ?? '?'} km of the '
                    '${f.point!.label.isEmpty ? 'chosen point' : 'map area'}',
                  ),
                  trailing: IconButton(
                    tooltip: 'Remove area',
                    icon: const Icon(Icons.close),
                    onPressed: () => _update(
                      (f) => f.copyWith(
                        point: () => null,
                        radiusKm: () => null,
                        sort: f.sort == GigSort.distance
                            ? GigSort.bestFit
                            : null,
                      ),
                    ),
                  ),
                ),
              heading('Dates'),
              OutlinedButton.icon(
                onPressed: _pickDates,
                icon: const Icon(Icons.date_range_outlined),
                label: Text(
                  f.startFrom == null
                      ? 'Starting any time'
                      : 'Starting ${shortDate(f.startFrom!)} to '
                            '${shortDate(f.startTo ?? f.startFrom!)}',
                ),
              ),
              if (f.startFrom != null)
                TextButton(
                  onPressed: () => _update(
                    (f) =>
                        f.copyWith(startFrom: () => null, startTo: () => null),
                  ),
                  child: const Text('Any dates'),
                ),
              heading('How long can you stay?'),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final days in _stayOptions)
                    ChoiceChip(
                      label: Text(
                        days < 30
                            ? '$days days'
                            : '${days ~/ 30} '
                                  '${days == 30 ? 'month' : 'months'}',
                      ),
                      selected: f.minStay == days,
                      onSelected: (on) => _update(
                        (f) => f.copyWith(minStay: () => on ? days : null),
                      ),
                    ),
                ],
              ),
              const SizedBox(height: 12),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Verified hosts only'),
                subtitle: const Text('ID and property checked by Barterly'),
                value: f.verifiedHosts,
                onChanged: (on) =>
                    _update((f) => f.copyWith(verifiedHosts: on)),
              ),
              const SizedBox(height: 8),
              TextButton.icon(
                onPressed: _saveSearch,
                icon: const Icon(Icons.notifications_active_outlined),
                label: const Text('Save this search and get alerts'),
              ),
            ],
          ),
        ),
        SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 8, 20, 12),
            child: SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: () => Navigator.pop(context, _result),
                child: const Text('Show gigs'),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _SavedSearches extends ConsumerWidget {
  const new();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final saved = ref.watch(savedSearchesProvider).value ?? const [];
    if (saved.isEmpty) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(top: 8, bottom: 8),
          child: Text(
            'Saved searches',
            style: Theme.of(context).textTheme.titleMedium,
          ),
        ),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final s in saved)
              InputChip(
                label: Text(s.name),
                onPressed: () => Navigator.pop(context, s.filters),
                deleteButtonTooltipMessage: 'Delete ${s.name}',
                onDeleted: () async {
                  try {
                    await ref
                        .read(gigsRepositoryProvider)
                        .deleteSavedSearch(s.id);
                  } on ApiError {
                    // Still listed after the refresh: nothing else to do.
                  }
                  ref.invalidate(savedSearchesProvider);
                },
              ),
          ],
        ),
      ],
    );
  }
}

class _NameDialog extends StatefulWidget {
  const new();

  @override
  State<_NameDialog> createState() => _NameDialogState();
}

class _NameDialogState extends State<_NameDialog> {
  final _name = TextEditingController();

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Name this search'),
    content: TextField(
      controller: _name,
      autofocus: true,
      maxLength: 80,
      decoration: const InputDecoration(hintText: 'Goa barter stays'),
      onSubmitted: (value) => Navigator.pop(context, value),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Cancel'),
      ),
      FilledButton(
        onPressed: () => Navigator.pop(context, _name.text),
        child: const Text('Save'),
      ),
    ],
  );
}
