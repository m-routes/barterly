import 'dart:async';

import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/auth/session.dart';
import 'package:barterly/src/providers.dart';
import 'package:barterly/src/reviews/review_models.dart';
import 'package:barterly/src/theme/tokens.dart';
import 'package:barterly/src/widgets/feedback.dart';
import 'package:barterly/src/widgets/states.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import 'package:material_ui/material_ui.dart';

/// Reviewing a completed stay. Double-blind: neither side sees the other's
/// review until both are in, or the 14-day window closes.
class StayReviewScreen extends ConsumerStatefulWidget {
  const new({required this.bookingId, super.key});

  final String bookingId;

  @override
  ConsumerState<StayReviewScreen> createState() => _StayReviewScreenState();
}

class _StayReviewScreenState extends ConsumerState<StayReviewScreen> {
  Future<BookingReviews>? _data;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  void _reload() => setState(() {
    _data = ref.read(reviewsRepositoryProvider).forBooking(widget.bookingId);
  });

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Review your stay')),
    body: FutureBuilder<BookingReviews>(
      future: _data,
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          final e = snapshot.error;
          return ErrorView(
            title: "We couldn't load the reviews",
            message: e is ApiError ? e.userMessage : '$e',
            onRetry: _reload,
          );
        }
        final data = snapshot.data;
        if (data == null) return const LoadingView();
        return ListView(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
          children: [
            if (data.canReview)
              _ReviewForm(
                data: data,
                bookingId: widget.bookingId,
                onDone: _reload,
              ),
            if (data.mine case final mine?) ...[
              _ReviewView(review: mine, heading: 'Your review'),
              if (!mine.published)
                Padding(
                  padding: const EdgeInsets.only(top: BarterlySpace.xs),
                  child: Text(
                    mine.status == 'held'
                        ? "Barterly is checking it before it's published."
                        : 'Hidden until your host reviews too, or the '
                              'window closes.',
                  ),
                ),
              const SizedBox(height: BarterlySpace.md),
            ],
            if (data.theirs case final theirs?)
              _ReviewView(
                review: theirs,
                heading: "Your host's review of you",
                onReplied: _reload,
                canReply: true,
              )
            else if (data.theyHaveReviewed)
              const Text(
                "Your host has reviewed you. You'll see it once you review "
                'them, or when the window closes.',
              ),
          ],
        );
      },
    ),
  );
}

class _StarRow extends StatelessWidget {
  const new({
    required this.label,
    required this.value,
    required this.onChanged,
  });

  final String label;
  final int value;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) => Row(
    children: [
      Expanded(child: Text(label)),
      for (var n = 1; n <= 5; n++)
        IconButton(
          tooltip: '$label: $n out of 5',
          isSelected: n <= value,
          onPressed: () => onChanged(n),
          icon: Icon(
            n <= value ? Icons.star : Icons.star_border,
            color: BarterlyColors.accent,
          ),
        ),
    ],
  );
}

class _ReviewForm extends ConsumerStatefulWidget {
  const new({
    required this.data,
    required this.bookingId,
    required this.onDone,
  });

  final BookingReviews data;
  final String bookingId;
  final VoidCallback onDone;

  @override
  ConsumerState<_ReviewForm> createState() => _ReviewFormState();
}

class _ReviewFormState extends ConsumerState<_ReviewForm> {
  int _rating = 0;
  final Map<String, int> _scores = {for (final c in reviewCategories) c: 0};
  final _text = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  bool get _complete =>
      _rating > 0 &&
      _scores.values.every((s) => s > 0) &&
      _text.text.trim().length >= 20;

  Future<void> _send() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref
          .read(reviewsRepositoryProvider)
          .submit(
            widget.bookingId,
            rating: _rating,
            scores: _scores,
            text: _text.text.trim(),
          );
      widget.onDone();
    } on ApiError catch (e) {
      if (mounted) {
        setState(() {
          _busy = false;
          _error = e.userMessage;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final closes = widget.data.windowClosesAt;
    return SurfaceCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        spacing: BarterlySpace.xs,
        children: [
          Text(
            'Review your host',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          if (closes != null)
            Text(
              'By ${DateFormat('d MMM').format(closes.toLocal())}. Neither of '
              "you sees the other's review until both are in. It can't be "
              'changed once published.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          _StarRow(
            label: 'Overall',
            value: _rating,
            onChanged: (v) => setState(() => _rating = v),
          ),
          for (final c in reviewCategories)
            _StarRow(
              label: widget.data.categoryLabels[c] ?? c,
              value: _scores[c]!,
              onChanged: (v) => setState(() => _scores[c] = v),
            ),
          TextField(
            controller: _text,
            maxLength: 2000,
            minLines: 3,
            maxLines: 8,
            decoration: const InputDecoration(
              labelText: 'Your review',
              helperText: 'At least 20 characters. No phone numbers or links.',
            ),
            onChanged: (_) => setState(() {}),
          ),
          if (_error != null)
            Text(_error!, style: const TextStyle(color: BarterlyColors.danger)),
          FilledButton(
            onPressed: _complete && !_busy ? _send : null,
            child: Text(_busy ? 'Sending…' : 'Submit review'),
          ),
        ],
      ),
    );
  }
}

class _ReviewView extends ConsumerWidget {
  const new({
    required this.review,
    required this.heading,
    this.onReplied,
    this.canReply = false,
  });

  final StayReview review;
  final String heading;
  final VoidCallback? onReplied;
  final bool canReply;

  @override
  Widget build(BuildContext context, WidgetRef ref) => SurfaceCard(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      spacing: BarterlySpace.xs,
      children: [
        Text(heading, style: Theme.of(context).textTheme.titleMedium),
        Semantics(
          label: '${review.rating} out of 5 stars',
          excludeSemantics: true,
          child: Text('★' * review.rating + '☆' * (5 - review.rating)),
        ),
        for (final c in review.categories)
          Text(
            '${c.label}: ${c.score}/5',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        Text(review.text),
        if (review.reply case final reply?)
          Text('Reply: $reply', style: Theme.of(context).textTheme.bodySmall)
        else if (canReply && review.published)
          TextButton(
            onPressed: () async {
              final sent = await showDialog<bool>(
                context: context,
                builder: (_) => _ReplyDialog(reviewId: review.id),
              );
              if (sent ?? false) onReplied?.call();
            },
            child: const Text('Reply'),
          ),
      ],
    ),
  );
}

class _ReplyDialog extends ConsumerStatefulWidget {
  const new({required this.reviewId});

  final String reviewId;

  @override
  ConsumerState<_ReplyDialog> createState() => _ReplyDialogState();
}

class _ReplyDialogState extends ConsumerState<_ReplyDialog> {
  final _text = TextEditingController();
  String? _error;

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Reply to this review'),
    content: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const Text("You can reply once, and it can't be changed after."),
        TextField(
          controller: _text,
          maxLength: 1000,
          decoration: const InputDecoration(labelText: 'Your reply'),
          onChanged: (_) => setState(() {}),
        ),
        if (_error != null)
          Text(_error!, style: const TextStyle(color: BarterlyColors.danger)),
      ],
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.of(context).pop(false),
        child: const Text('Cancel'),
      ),
      FilledButton(
        onPressed: _text.text.trim().isEmpty
            ? null
            : () async {
                try {
                  await ref
                      .read(reviewsRepositoryProvider)
                      .reply(widget.reviewId, _text.text.trim());
                  if (context.mounted) Navigator.of(context).pop(true);
                } on ApiError catch (e) {
                  setState(() => _error = e.userMessage);
                }
              },
        child: const Text('Post reply'),
      ),
    ],
  );
}

String _responseTime(int minutes) {
  if (minutes < 60) return '$minutes min';
  final hours = (minutes / 60).round();
  return hours < 48 ? '$hours h' : '${(hours / 24).round()} days';
}

/// Your reputation as talent, and the reviews hosts have left you.
class MyReviewsScreen extends ConsumerStatefulWidget {
  const new({super.key});

  @override
  ConsumerState<MyReviewsScreen> createState() => _MyReviewsScreenState();
}

class _MyReviewsScreenState extends ConsumerState<MyReviewsScreen> {
  Future<(Reputation, List<StayReview>)>? _data;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  void _reload() {
    final session = ref.read(sessionProvider);
    if (session is! SignedIn) return;
    final repo = ref.read(reviewsRepositoryProvider);
    final id = session.user.id;
    setState(() {
      _data = (repo.reputation(id), repo.aboutMe(id)).wait;
    });
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Reviews and reputation')),
    body: FutureBuilder<(Reputation, List<StayReview>)>(
      future: _data,
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          return ErrorView(
            title: "We couldn't load your reviews",
            message: 'Check your connection and try again.',
            onRetry: _reload,
          );
        }
        final data = snapshot.data;
        if (data == null) return const LoadingView();
        final (reputation, reviews) = data;
        final rating = reputation.ratingAverage;
        return ListView(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
          children: [
            SurfaceCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                spacing: BarterlySpace.xs,
                children: [
                  Text(
                    rating == null
                        ? 'No reviews yet'
                        : '★ ${rating.toStringAsFixed(1)} from '
                              '${reputation.reviewCount} review'
                              '${reputation.reviewCount == 1 ? '' : 's'}',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  if (reputation.completionRate case final rate?)
                    Text('$rate% of stays completed'),
                  if (reputation.responseMinutes case final m?)
                    Text('You reply in about ${_responseTime(m)}'),
                  if (reputation.badges.isNotEmpty)
                    Wrap(
                      spacing: BarterlySpace.xs,
                      children: [
                        for (final b in reputation.badges) Tag(label: b),
                      ],
                    ),
                ],
              ),
            ),
            const SizedBox(height: BarterlySpace.md),
            for (final r in reviews) ...[
              _ReviewView(
                review: r,
                heading: r.authorName,
                canReply: true,
                onReplied: _reload,
              ),
              const SizedBox(height: BarterlySpace.sm),
            ],
          ],
        );
      },
    ),
  );
}
