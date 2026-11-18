import 'dart:async';

import 'package:barterly/src/agreements/agreement_models.dart';
import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/apply/application.dart';
import 'package:barterly/src/apply/outbox.dart' show myApplicationsProvider;
import 'package:barterly/src/discover/gig.dart' show dateRange, shortDate;
import 'package:barterly/src/platform/calendar.dart';
import 'package:barterly/src/providers.dart';
import 'package:barterly/src/router.dart' show Routes;
import 'package:barterly/src/theme/tokens.dart';
import 'package:barterly/src/trips/trip_models.dart';
import 'package:barterly/src/widgets/feedback.dart';
import 'package:barterly/src/widgets/states.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

/// One trip, as the canvas's booking screen tracks it: the progress bar, what's
/// next, the interview (pick a time, add it to the calendar), the offer, the
/// agreement and check-in, the chat, and every status change so far.
class TripScreen extends ConsumerWidget {
  const new({required this.applicationId, super.key});

  final String applicationId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final detail = ref.watch(applicationDetailProvider(applicationId));
    return Scaffold(
      appBar: AppBar(title: const Text('Trip')),
      body: switch (detail) {
        AsyncData(:final value) => RefreshIndicator(
          onRefresh: () async =>
              ref.invalidate(applicationDetailProvider(applicationId)),
          child: _TripBody(detail: value),
        ),
        AsyncError(:final error) => ErrorView(
          title: "We couldn't load this trip",
          message: error is ApiError ? error.userMessage : '$error',
          onRetry: () =>
              ref.invalidate(applicationDetailProvider(applicationId)),
        ),
        _ => const LoadingView(label: 'Loading your trip…'),
      },
    );
  }
}

class _TripBody extends ConsumerStatefulWidget {
  const new({required this.detail});

  final ApplicationDetail detail;

  @override
  ConsumerState<_TripBody> createState() => _TripBodyState();
}

class _TripBodyState extends ConsumerState<_TripBody> {
  Future<Agreement?>? _agreement;

  @override
  void initState() {
    super.initState();
    _agreement = _loadAgreement();
  }

  @override
  void didUpdateWidget(covariant _TripBody old) {
    super.didUpdateWidget(old);
    if (old.detail.application.agreementId !=
        widget.detail.application.agreementId) {
      _agreement = _loadAgreement();
    }
  }

  Future<Agreement?> _loadAgreement() async {
    final id = widget.detail.application.agreementId;
    if (id == null) return null;
    try {
      return await ref.read(agreementsRepositoryProvider).agreement(id);
    } on ApiError {
      return null; // the trip still shows; the agreement button opens it
    }
  }

  void _refresh() {
    ref
      ..invalidate(applicationDetailProvider(widget.detail.application.id))
      ..invalidate(myApplicationsProvider);
  }

  @override
  Widget build(BuildContext context) {
    final a = widget.detail.application;
    final interview = widget.detail.interview;
    return FutureBuilder<Agreement?>(
      future: _agreement,
      builder: (context, snapshot) {
        final agreement = snapshot.data;
        final progress = tripProgress(
          a.status,
          bookingStatus: agreement?.bookingStatus ?? '',
          interview: interview,
        );
        final stay = agreement == null ? null : _stayOf(agreement);
        return ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
          children: [
            SurfaceCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                spacing: BarterlySpace.sm,
                children: [
                  Row(
                    children: [
                      Tag(
                        label: progress.ended.isNotEmpty
                            ? progress.ended
                            : _statusLabel(a, agreement),
                        background: progress.ended.isNotEmpty
                            ? BarterlyColors.surfaceSunken
                            : BarterlyColors.accentSoft,
                        foreground: progress.ended.isNotEmpty
                            ? BarterlyColors.inkMuted
                            : BarterlyColors.onAccentSoft,
                      ),
                    ],
                  ),
                  Text(
                    a.gigTitle,
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  if (stay != null)
                    Text(
                      dateRange(stay.$1, stay.$2),
                      style: const TextStyle(color: BarterlyColors.inkMuted),
                    )
                  else if (a.proposedStart != null && a.proposedEnd != null)
                    Text(
                      'You asked for '
                      '${dateRange(a.proposedStart!, a.proposedEnd!)}',
                      style: const TextStyle(color: BarterlyColors.inkMuted),
                    ),
                  TripTracker(progress: progress),
                  if (progress.next.isNotEmpty)
                    Text(
                      'Next: ${progress.next}',
                      style: const TextStyle(
                        fontSize: 13,
                        color: BarterlyColors.inkMuted,
                      ),
                    ),
                ],
              ),
            ),
            if (interview != null &&
                interview.status != InterviewStatus.cancelled) ...[
              const SizedBox(height: BarterlySpace.md),
              InterviewCard(
                applicationId: a.id,
                gigTitle: a.gigTitle,
                interview: interview,
                onChanged: _refresh,
              ),
            ],
            if (stay != null &&
                const {
                  'signing',
                  'confirmed',
                }.contains(agreement!.bookingStatus)) ...[
              const SizedBox(height: BarterlySpace.md),
              _CheckInCard(
                gigTitle: a.gigTitle,
                start: stay.$1,
                confirmed: agreement.bookingStatus == 'confirmed',
              ),
            ],
            const SizedBox(height: BarterlySpace.md),
            Wrap(
              spacing: BarterlySpace.sm,
              runSpacing: BarterlySpace.sm,
              children: [
                if (a.status == ApplicationStatus.offered)
                  FilledButton(
                    onPressed: () async {
                      await context.push(Routes.offer(a.id));
                      _refresh();
                    },
                    child: const Text('Review the offer'),
                  ),
                if (a.agreementId case final id?)
                  OutlinedButton.icon(
                    onPressed: () async {
                      await context.push(Routes.agreement(id));
                      setState(() => _agreement = _loadAgreement());
                      _refresh();
                    },
                    icon: const Icon(Icons.description_outlined, size: 18),
                    label: Text(
                      agreement?.bookingStatus == 'signing'
                          ? 'Sign the agreement'
                          : 'Agreement',
                    ),
                  ),
                if (a.conversationId case final id?)
                  OutlinedButton.icon(
                    onPressed: () async {
                      await context.push(Routes.chat(id));
                      _refresh();
                    },
                    icon: const Icon(Icons.chat_bubble_outline, size: 18),
                    label: Text(
                      a.unreadMessages > 0
                          ? 'Message the host (${a.unreadMessages} new)'
                          : 'Message the host',
                    ),
                  ),
              ],
            ),
            const SizedBox(height: BarterlySpace.lg),
            Semantics(
              header: true,
              child: Text(
                'What happened',
                style: Theme.of(context).textTheme.titleMedium,
              ),
            ),
            const SizedBox(height: BarterlySpace.sm),
            StatusTimeline(entries: widget.detail.timeline),
          ],
        );
      },
    );
  }

  String _statusLabel(Application a, Agreement? agreement) =>
      switch (agreement?.bookingStatus) {
        'signing' => 'Awaiting signatures',
        'confirmed' => 'Confirmed',
        'checked_in' => 'Checked in',
        'delivering' => 'On your stay',
        'completed' || 'reviewed' => 'Completed',
        _ => a.status.label,
      };

  /// The stay's dates from the agreement version in force (or being signed).
  (DateTime, DateTime)? _stayOf(Agreement agreement) {
    if (agreement.versions.isEmpty) return null;
    final version =
        agreement.versions
            .where((v) => v.number == agreement.currentVersion)
            .firstOrNull ??
        agreement.versions.first;
    return (version.terms.startDate, version.terms.endDate);
  }
}

/// The canvas's segmented progress bar, read out as "n of 7 steps done".
class TripTracker extends StatelessWidget {
  const new({required this.progress, super.key});

  final TripProgress progress;

  @override
  Widget build(BuildContext context) {
    const steps = TripStep.values;
    final current = steps[(progress.done - 1).clamp(0, steps.length - 1)];
    return Semantics(
      label:
          'Progress: ${current.label}, ${progress.done} of ${steps.length} '
          'steps done${progress.ended.isEmpty ? '' : '. ${progress.ended}'}',
      excludeSemantics: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        spacing: BarterlySpace.xs,
        children: [
          Row(
            spacing: 4,
            children: [
              for (var i = 0; i < steps.length; i++)
                Expanded(
                  child: Container(
                    height: 6,
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(3),
                      color: i < progress.done
                          ? (progress.ended.isEmpty
                                ? BarterlyColors.accent
                                : BarterlyColors.inkMuted)
                          : BarterlyColors.border,
                    ),
                  ),
                ),
            ],
          ),
          Text(
            '${current.label} · ${progress.done} of ${steps.length}',
            style: const TextStyle(
              fontSize: 12,
              color: BarterlyColors.inkMuted,
            ),
          ),
        ],
      ),
    );
  }
}

/// Every status change, newest first, with the reason the host gave.
class StatusTimeline extends StatelessWidget {
  const new({required this.entries, super.key});

  final List<TimelineEntry> entries;

  @override
  Widget build(BuildContext context) {
    if (entries.isEmpty) {
      return const Text(
        'Nothing yet.',
        style: TextStyle(color: BarterlyColors.inkMuted),
      );
    }
    final newest = [...entries]..sort((a, b) => b.at.compareTo(a.at));
    return Column(
      children: [
        for (final (i, e) in newest.indexed)
          IntrinsicHeight(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                SizedBox(
                  width: 24,
                  child: Column(
                    children: [
                      Container(
                        width: 12,
                        height: 12,
                        margin: const EdgeInsets.only(top: 4),
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: i == 0
                              ? BarterlyColors.accent
                              : BarterlyColors.border,
                        ),
                      ),
                      if (i < newest.length - 1)
                        Expanded(
                          child: Container(
                            width: 2,
                            color: BarterlyColors.border,
                          ),
                        ),
                    ],
                  ),
                ),
                const SizedBox(width: BarterlySpace.sm),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.only(bottom: BarterlySpace.md),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      spacing: 2,
                      children: [
                        Text(
                          e.status.label,
                          style: const TextStyle(fontWeight: FontWeight.w600),
                        ),
                        Text(
                          shortDate(e.at.toLocal()),
                          style: const TextStyle(
                            fontSize: 13,
                            color: BarterlyColors.inkMuted,
                          ),
                        ),
                        if (e.reason.isNotEmpty) Text(e.reason),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

/// The interview: pick one of the host's times, ask for others, join the call,
/// and put it in the calendar.
class InterviewCard extends ConsumerStatefulWidget {
  const new({
    required this.applicationId,
    required this.gigTitle,
    required this.interview,
    required this.onChanged,
    super.key,
  });

  final String applicationId;
  final String gigTitle;
  final Interview interview;
  final VoidCallback onChanged;

  @override
  ConsumerState<InterviewCard> createState() => _InterviewCardState();
}

class _InterviewCardState extends ConsumerState<InterviewCard> {
  int? _slot;
  bool _busy = false;

  void _show(String message) =>
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(message)));

  Future<void> _pick() async {
    setState(() => _busy = true);
    try {
      await ref
          .read(applicationsRepositoryProvider)
          .pickInterviewSlot(widget.applicationId, _slot!);
      if (mounted) _show('Interview booked.');
      widget.onChanged();
    } on ApiError catch (error) {
      if (mounted) _show(error.userMessage);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _askForOthers() async {
    final note = TextEditingController();
    final send = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Ask for other times?'),
        content: TextField(
          controller: note,
          maxLength: 500,
          decoration: const InputDecoration(
            labelText: 'When suits you (optional)',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Ask the host'),
          ),
        ],
      ),
    );
    if (send != true || !mounted) return;
    setState(() => _busy = true);
    try {
      await ref
          .read(applicationsRepositoryProvider)
          .askForNewTimes(widget.applicationId, note: note.text.trim());
      if (mounted) _show('Asked the host for other times.');
      widget.onChanged();
    } on ApiError catch (error) {
      if (mounted) _show(error.userMessage);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _addToCalendar(Interview i) async {
    final start = i.startsAt!.toLocal();
    final added = await ref
        .read(calendarProvider)
        .add(
          CalendarEvent(
            title: 'Barterly interview: ${widget.gigTitle}',
            start: start,
            end: start.add(Duration(minutes: i.durationMinutes)),
            description: [
              'Video interview with the host.',
              if (i.videoLink.isNotEmpty) i.videoLink,
              if (i.note.isNotEmpty) i.note,
            ].join('\n'),
            location: i.videoLink,
            url: i.videoLink,
          ),
        );
    if (mounted && !added) _show('No calendar app could take it.');
  }

  @override
  Widget build(BuildContext context) {
    final i = widget.interview;
    return SurfaceCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        spacing: BarterlySpace.sm,
        children: [
          Text('Interview', style: Theme.of(context).textTheme.titleMedium),
          if (i.note.isNotEmpty) Text('“${i.note}”'),
          switch (i.status) {
            InterviewStatus.proposed => Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Pick a time that works (India time).'),
                RadioGroup<int>(
                  groupValue: _slot,
                  onChanged: (v) => setState(() => _slot = v),
                  child: Column(
                    children: [
                      for (final s in i.slots)
                        RadioListTile<int>(
                          contentPadding: EdgeInsets.zero,
                          value: s.id,
                          title: Text(s.label),
                          subtitle: Text('${i.durationMinutes} minutes'),
                        ),
                    ],
                  ),
                ),
                Wrap(
                  spacing: BarterlySpace.sm,
                  children: [
                    FilledButton(
                      onPressed: _busy || _slot == null
                          ? null
                          : () => unawaited(_pick()),
                      child: Text(_busy ? 'Booking…' : 'Book this time'),
                    ),
                    TextButton(
                      onPressed: _busy
                          ? null
                          : () => unawaited(_askForOthers()),
                      child: const Text('None of these work'),
                    ),
                  ],
                ),
              ],
            ),
            InterviewStatus.scheduled => Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              spacing: BarterlySpace.sm,
              children: [
                Text(
                  '${i.startsAtLabel} · ${i.durationMinutes} minutes',
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
                Wrap(
                  spacing: BarterlySpace.sm,
                  runSpacing: BarterlySpace.sm,
                  children: [
                    if (i.videoLink.isNotEmpty)
                      FilledButton.icon(
                        onPressed: () => unawaited(
                          ref
                              .read(urlOpenerProvider)
                              .openExternal(Uri.parse(i.videoLink)),
                        ),
                        icon: const Icon(Icons.videocam_outlined, size: 18),
                        label: const Text('Join the call'),
                      ),
                    if (i.startsAt != null)
                      OutlinedButton.icon(
                        onPressed: () => unawaited(_addToCalendar(i)),
                        icon: const Icon(Icons.event_outlined, size: 18),
                        label: const Text('Add to calendar'),
                      ),
                  ],
                ),
              ],
            ),
            InterviewStatus.newTimesRequested => const Text(
              'You asked for other times. The host will send new ones.',
              style: TextStyle(color: BarterlyColors.inkMuted),
            ),
            InterviewStatus.cancelled => const SizedBox.shrink(),
          },
        ],
      ),
    );
  }
}

/// Check-in: the first day of the stay, with a calendar reminder the day
/// before.
class _CheckInCard extends ConsumerWidget {
  const new({
    required this.gigTitle,
    required this.start,
    required this.confirmed,
  });

  final String gigTitle;
  final DateTime start;
  final bool confirmed;

  @override
  Widget build(BuildContext context, WidgetRef ref) => SurfaceCard(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      spacing: BarterlySpace.sm,
      children: [
        Text('Check-in', style: Theme.of(context).textTheme.titleMedium),
        Text(
          confirmed
              ? 'Your stay starts ${shortDate(start)}. The address and '
                    "host's phone are on the agreement screen."
              : 'Your stay would start ${shortDate(start)}, once you both '
                    'sign.',
        ),
        OutlinedButton.icon(
          onPressed: () async {
            final messenger = ScaffoldMessenger.of(context);
            final added = await ref
                .read(calendarProvider)
                .add(
                  CalendarEvent(
                    title: 'Check in: $gigTitle',
                    start: start,
                    end: start.add(const Duration(days: 1)),
                    allDay: true,
                    remindBefore: const Duration(days: 1),
                    description:
                        'Your Barterly stay starts today. Directions and the '
                        "host's phone are in the app.",
                  ),
                );
            if (!added) {
              messenger.showSnackBar(
                const SnackBar(content: Text('No calendar app could take it.')),
              );
            }
          },
          icon: const Icon(Icons.event_outlined, size: 18),
          label: const Text('Add check-in to calendar'),
        ),
      ],
    ),
  );
}
