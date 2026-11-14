import 'dart:async';

import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/apply/application.dart';
import 'package:barterly/src/apply/outbox.dart';
import 'package:barterly/src/discover/gig.dart' show dateRange, shortDate;
import 'package:barterly/src/providers.dart';
import 'package:barterly/src/theme/tokens.dart';
import 'package:barterly/src/widgets/feedback.dart';
import 'package:barterly/src/widgets/states.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

/// My trips: applications waiting to send, and applications the host has.
class MyApplicationsScreen extends ConsumerWidget {
  const new({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final drafts = ref.watch(outboxProvider);
    final applications = ref.watch(myApplicationsProvider);
    Future<void> refresh() async {
      unawaited(ref.read(outboxProvider.notifier).flush());
      ref.invalidate(myApplicationsProvider);
      await ref.read(myApplicationsProvider.future).catchError((_) {
        return const <Application>[];
      });
    }

    final Widget body;
    final list = applications.value;
    if (list == null && applications.hasError && drafts.isEmpty) {
      final error = applications.error;
      body = _scrollable(
        ErrorView(
          title: error is ApiError && error.code == 'network_error'
              ? "You're offline"
              : "We couldn't load your applications",
          message: error is ApiError
              ? error.userMessage
              : 'Something went wrong. Try again.',
          onRetry: () => ref.invalidate(myApplicationsProvider),
        ),
      );
    } else if (list == null && drafts.isEmpty) {
      body = const SkeletonList(
        label: 'Loading your applications',
        itemBuilder: _skeletonRow,
      );
    } else if (drafts.isEmpty && (list?.isEmpty ?? true)) {
      body = _scrollable(
        EmptyState(
          icon: Icons.luggage_outlined,
          title: 'No trips yet',
          message:
              'Apply to a gig and it shows up here. When a host accepts you, '
              'your stay, dates and agreement show up here too.',
          action: FilledButton(
            onPressed: () => context.go('/discover'),
            child: const Text('Find a gig'),
          ),
        ),
      );
    } else {
      body = ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
        children: [
          if (drafts.isNotEmpty) ...[
            const _Section('Waiting to send'),
            for (final d in drafts) _DraftCard(draft: d),
          ],
          if (applications.hasError && list == null)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 12),
              child: Text(
                "Your sent applications will show when you're back online.",
                style: TextStyle(color: BarterlyColors.inkMuted),
              ),
            ),
          if (list != null && list.isNotEmpty) ...[
            const _Section('Applications'),
            for (final a in list) _ApplicationCard(application: a),
          ],
        ],
      );
    }
    return Scaffold(
      appBar: AppBar(title: const Text('My trips')),
      body: RefreshIndicator(onRefresh: refresh, child: body),
    );
  }

  static Widget _scrollable(Widget child) => CustomScrollView(
    physics: const AlwaysScrollableScrollPhysics(),
    slivers: [SliverFillRemaining(hasScrollBody: false, child: child)],
  );

  static Widget _skeletonRow(BuildContext context) => const SurfaceCard(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      spacing: 10,
      children: [
        SkeletonBox(width: 90, height: 22),
        SkeletonBox(width: 240, height: 18),
        SkeletonBox(width: 160),
      ],
    ),
  );
}

class _Section extends StatelessWidget {
  const new(this.title);
  final String title;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 12, bottom: 8),
    child: Semantics(
      header: true,
      child: Text(title, style: Theme.of(context).textTheme.titleMedium),
    ),
  );
}

class _DraftCard extends ConsumerWidget {
  const new({required this.draft});

  final ApplicationDraft draft;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final outbox = ref.read(outboxProvider.notifier);
    final attention = draft.status == DraftStatus.needsAttention;
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: SurfaceCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          spacing: 8,
          children: [
            Tag(
              label: switch (draft.status) {
                DraftStatus.queued => 'Waiting for network',
                DraftStatus.sending => 'Sending…',
                DraftStatus.needsAttention => 'Not sent',
              },
              icon: attention
                  ? Icons.error_outline
                  : Icons.cloud_upload_outlined,
              background: attention
                  ? BarterlyColors.dangerSoft
                  : BarterlyColors.accentSoft,
              foreground: attention
                  ? BarterlyColors.danger
                  : BarterlyColors.onAccentSoft,
            ),
            Text(
              draft.gigTitle,
              style: Theme.of(context).textTheme.titleMedium,
            ),
            Text(
              [
                if (draft.place.isNotEmpty) draft.place,
                dateRange(draft.proposedStart, draft.proposedEnd),
              ].join(' · '),
              style: const TextStyle(color: BarterlyColors.inkMuted),
            ),
            for (final p in draft.problems)
              Text(
                '• $p',
                style: const TextStyle(color: BarterlyColors.danger),
              ),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                TextButton(
                  onPressed: draft.status == DraftStatus.sending
                      ? null
                      : () => _confirmDelete(context, outbox),
                  child: const Text('Delete'),
                ),
                if (attention)
                  FilledButton(
                    onPressed: () => unawaited(outbox.retry(draft.localId)),
                    child: const Text('Try again'),
                  )
                else if (draft.status == DraftStatus.queued)
                  OutlinedButton(
                    onPressed: () => unawaited(outbox.flush()),
                    child: const Text('Send now'),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _confirmDelete(BuildContext context, Outbox outbox) async {
    final yes = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete this application?'),
        content: const Text(
          "It hasn't been sent, so the host never sees it. This can't be "
          'undone.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Keep'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (yes ?? false) await outbox.remove(draft.localId);
  }
}

class _ApplicationCard extends ConsumerStatefulWidget {
  const new({required this.application});

  final Application application;

  @override
  ConsumerState<_ApplicationCard> createState() => _ApplicationCardState();
}

class _ApplicationCardState extends ConsumerState<_ApplicationCard> {
  bool _busy = false;

  Future<void> _withdraw() async {
    final yes = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Withdraw your application?'),
        content: const Text(
          'The host will no longer see it. You can apply again later while '
          'the gig is open.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Keep it'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Withdraw'),
          ),
        ],
      ),
    );
    if (!(yes ?? false) || !mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    setState(() => _busy = true);
    try {
      await ref
          .read(applicationsRepositoryProvider)
          .withdraw(widget.application.id);
      ref.invalidate(myApplicationsProvider);
      messenger.showSnackBar(
        const SnackBar(content: Text('Application withdrawn.')),
      );
    } on ApiError catch (error) {
      messenger.showSnackBar(SnackBar(content: Text(error.userMessage)));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final a = widget.application;
    final active = a.status.active;
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: SurfaceCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          spacing: 8,
          children: [
            Row(
              children: [
                Tag(
                  label: a.status.label,
                  background: active
                      ? BarterlyColors.accentSoft
                      : BarterlyColors.surfaceSunken,
                  foreground: active
                      ? BarterlyColors.onAccentSoft
                      : BarterlyColors.inkMuted,
                ),
                const Spacer(),
                if (a.appliedAt != null)
                  Text(
                    'Applied ${shortDate(a.appliedAt!.toLocal())}',
                    style: const TextStyle(
                      fontSize: 13,
                      color: BarterlyColors.inkMuted,
                    ),
                  ),
              ],
            ),
            Text(a.gigTitle, style: Theme.of(context).textTheme.titleMedium),
            if (a.proposedStart != null && a.proposedEnd != null)
              Text(
                [
                  dateRange(a.proposedStart!, a.proposedEnd!),
                  if (a.attachmentCount > 0) '${a.attachmentCount} attached',
                ].join(' · '),
                style: const TextStyle(color: BarterlyColors.inkMuted),
              ),
            if (active)
              Align(
                alignment: Alignment.centerRight,
                child: TextButton(
                  onPressed: _busy ? null : _withdraw,
                  child: Text(_busy ? 'Withdrawing…' : 'Withdraw'),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
