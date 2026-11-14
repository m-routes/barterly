import 'dart:async';

import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/apply/outbox.dart';
import 'package:barterly/src/discover/discover_controller.dart';
import 'package:barterly/src/discover/gig.dart';
import 'package:barterly/src/profile/talent_profile.dart' show languageNames;
import 'package:barterly/src/theme/tokens.dart';
import 'package:barterly/src/widgets/feedback.dart';
import 'package:barterly/src/widgets/states.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

const _fitLabels = {
  'skills': 'Skills',
  'reliability': 'Reliability',
  'ratings': 'Ratings',
  'audience_quality': 'Audience',
  'distance_availability': 'Distance and dates',
};

/// One gig (design canvas: TalentGig).
class GigDetailScreen extends ConsumerWidget {
  const new({required this.gigId, super.key});

  final String gigId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final gig = ref.watch(gigProvider(gigId));
    return Scaffold(
      body: switch (gig) {
        AsyncData(:final value) => RefreshIndicator(
          onRefresh: () => ref.refresh(gigProvider(gigId).future),
          child: _GigBody(gig: value),
        ),
        AsyncError(:final error) => SafeArea(
          child: Column(
            children: [
              const Align(alignment: Alignment.centerLeft, child: BackButton()),
              Expanded(
                child: ErrorView(
                  title: "We couldn't open this gig",
                  message: error is ApiError
                      ? error.userMessage
                      : 'Something went wrong. Try again.',
                  onRetry: () => ref.invalidate(gigProvider(gigId)),
                ),
              ),
            ],
          ),
        ),
        _ => const _GigSkeleton(),
      },
      bottomNavigationBar: gig.hasValue
          ? _ApplyBar(gig: gig.requireValue)
          : null,
    );
  }
}

class _GigSkeleton extends StatelessWidget {
  const new();

  @override
  Widget build(BuildContext context) => Semantics(
    label: 'Loading gig',
    liveRegion: true,
    child: const ExcludeSemantics(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SkeletonBox(height: 148, radius: 0),
          Padding(
            padding: EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              spacing: 12,
              children: [
                SkeletonBox(width: 140, height: 22),
                SkeletonBox(width: 300, height: 28),
                SkeletonBox(width: 220),
                SkeletonBox(height: 120),
              ],
            ),
          ),
        ],
      ),
    ),
  );
}

class _GigBody extends StatelessWidget {
  const new({required this.gig});

  final Gig gig;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = payModelColors(gig.payModel);
    final p = gig.property;
    final todo = [
      if (gig.description case final d? when d.trim().isNotEmpty)
        ...d.trim().split('\n').where((l) => l.trim().isNotEmpty),
      for (final d in gig.deliverables) d.label,
    ];
    return ListView(
      padding: EdgeInsets.zero,
      children: [
        Stack(
          children: [
            GigBanner(tint: colors.tint, height: 148),
            Positioned(
              left: 16,
              top: MediaQuery.paddingOf(context).top + 12,
              child: IconButton.filled(
                tooltip: 'Back to Discover',
                style: IconButton.styleFrom(
                  backgroundColor: BarterlyColors.surface,
                  foregroundColor: BarterlyColors.ink,
                ),
                onPressed: () => context.pop(),
                icon: const Icon(Icons.arrow_back),
              ),
            ),
          ],
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            spacing: 14,
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                spacing: 8,
                children: [
                  Row(
                    spacing: 8,
                    children: [
                      Tag(
                        label: gig.payModel?.label ?? 'Gig',
                        background: colors.background,
                        foreground: colors.foreground,
                      ),
                      Tag(label: '${gig.fit.score}% fit', outlined: true),
                    ],
                  ),
                  Semantics(
                    header: true,
                    child: Text(
                      gig.title,
                      style: theme.textTheme.headlineSmall?.copyWith(
                        height: 1.2,
                      ),
                    ),
                  ),
                  Text(
                    [
                      p.name,
                      [p.city, p.state].where((s) => s.isNotEmpty).join(', '),
                    ].where((s) => s.isNotEmpty).join(' · '),
                    style: const TextStyle(color: BarterlyColors.inkMuted),
                  ),
                  Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: [
                      if (gig.hostVerified) const _Check('ID verified host'),
                      if (p.verified) const _Check('Property verified'),
                      if (p.womenFriendly) const _Check('Women-friendly host'),
                    ],
                  ),
                ],
              ),
              _FactsGrid(
                facts: [
                  ('Work', gig.workSummary ?? 'See details'),
                  ('You get', gig.youGet),
                  ('Stay length', gig.stayLength),
                  (
                    'Slots',
                    [
                      '${gig.slots} ${gig.slots == 1 ? 'slot' : 'slots'}',
                      if (gig.wifi) 'Wi-Fi included',
                    ].join(' · '),
                  ),
                ],
              ),
              if (todo.isNotEmpty) ...[
                const _Heading('What you will do'),
                for (final line in todo)
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Padding(
                        padding: EdgeInsets.only(top: 7, right: 10),
                        child: Icon(Icons.circle, size: 6),
                      ),
                      Expanded(
                        child: Text(
                          line.trim(),
                          style: const TextStyle(height: 1.45),
                        ),
                      ),
                    ],
                  ),
              ],
              if (_requirements(gig).isNotEmpty) ...[
                const _Heading('Before you apply'),
                for (final r in _requirements(gig))
                  Row(
                    spacing: 8,
                    children: [
                      const Icon(
                        Icons.info_outline,
                        size: 18,
                        color: BarterlyColors.inkMuted,
                      ),
                      Expanded(child: Text(r)),
                    ],
                  ),
              ],
              if (gig.fit.breakdown.isNotEmpty) _FitBreakdown(fit: gig.fit),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: BarterlyColors.accentSoft,
                  borderRadius: BorderRadius.circular(14),
                ),
                child: const Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  spacing: 10,
                  children: [
                    Icon(
                      Icons.verified_user_outlined,
                      color: BarterlyColors.onAccentSoft,
                      size: 20,
                    ),
                    Expanded(
                      child: Text(
                        'Hours are capped at 6 a day with one day off a week. '
                        'Host contact details unlock only after you both '
                        'confirm and sign the agreement.',
                        style: TextStyle(
                          fontSize: 13,
                          height: 1.45,
                          color: BarterlyColors.onAccentSoft,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  static List<String> _requirements(Gig gig) => [
    ?gig.verificationNeeded,
    if (gig.languages.isNotEmpty)
      'Speaks ${gig.languages.map((l) => languageNames[l] ?? l).join(' or ')}',
    if (gig.minFollowers > 0) 'At least ${gig.minFollowers} followers',
    if (gig.minStayDays != null) 'Stays at least ${gig.minStayDays} days',
    if (gig.applyBy != null) 'Apply by ${shortDate(gig.applyBy!)}',
  ];
}

class _Heading extends StatelessWidget {
  const new(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Semantics(
    header: true,
    child: Text(
      text,
      style: Theme.of(context).textTheme.titleLarge?.copyWith(fontSize: 17),
    ),
  );
}

class _Check extends StatelessWidget {
  const new(this.label);
  final String label;

  @override
  Widget build(BuildContext context) => Tag(
    label: label,
    icon: Icons.check,
    background: BarterlyColors.accentSoft,
    foreground: BarterlyColors.onAccentSoft,
  );
}

class _FactsGrid extends StatelessWidget {
  const new({required this.facts});

  final List<(String, String)> facts;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, constraints) {
      final width = (constraints.maxWidth - 10) / 2;
      return Wrap(
        spacing: 10,
        runSpacing: 10,
        children: [
          for (final (label, value) in facts)
            SizedBox(
              width: width,
              child: SurfaceCard(
                radius: 14,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  spacing: 2,
                  children: [
                    Text(
                      label,
                      style: const TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w500,
                        color: BarterlyColors.inkMuted,
                      ),
                    ),
                    Text(
                      value,
                      style: const TextStyle(fontWeight: FontWeight.w600),
                    ),
                  ],
                ),
              ),
            ),
        ],
      );
    },
  );
}

class _FitBreakdown extends StatelessWidget {
  const new({required this.fit});

  final Fit fit;

  @override
  Widget build(BuildContext context) => SurfaceCard(
    radius: 14,
    padding: EdgeInsets.zero,
    child: Theme(
      data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
      child: ExpansionTile(
        title: Text('Why this is a ${fit.score}% fit'),
        childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
        children: [
          for (final c in fit.breakdown)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                spacing: 4,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          _fitLabels[c.key] ?? c.key,
                          style: const TextStyle(fontWeight: FontWeight.w600),
                        ),
                      ),
                      Text(
                        '${c.points.round()} of ${(c.weight * 100).round()}',
                      ),
                    ],
                  ),
                  LinearProgressIndicator(
                    value: c.value.clamp(0, 1),
                    semanticsLabel: _fitLabels[c.key] ?? c.key,
                    backgroundColor: BarterlyColors.surfaceSunken,
                  ),
                  Text(
                    c.neutral ? '${c.reason} (no data yet)' : c.reason,
                    style: const TextStyle(
                      fontSize: 13,
                      color: BarterlyColors.inkMuted,
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    ),
  );
}

class _ApplyBar extends ConsumerWidget {
  const new({required this.gig});

  final Gig gig;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final queued = ref.watch(outboxProvider).any((d) => d.gigId == gig.id);
    final applied =
        ref
            .watch(myApplicationsProvider)
            .value
            ?.any((a) => a.gigId == gig.id && a.status.active) ??
        false;
    final label = applied
        ? 'You applied'
        : queued
        ? 'Waiting to send'
        : 'Apply for this gig';
    return DecoratedBox(
      decoration: const BoxDecoration(
        color: BarterlyColors.surface,
        border: Border(top: BorderSide(color: BarterlyColors.border)),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 12),
          child: FilledButton(
            style: FilledButton.styleFrom(
              minimumSize: const Size.fromHeight(52),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
              ),
            ),
            onPressed: applied || queued
                ? null
                : () =>
                      unawaited(context.push('/discover/gig/${gig.id}/apply')),
            child: Text(label),
          ),
        ),
      ),
    );
  }
}
