import 'dart:async';

import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/apply/application.dart' show AttachmentKind;
import 'package:barterly/src/deliverables/deliverable_models.dart';
import 'package:barterly/src/platform/media_picker.dart';
import 'package:barterly/src/providers.dart';
import 'package:barterly/src/theme/tokens.dart';
import 'package:barterly/src/widgets/feedback.dart';
import 'package:barterly/src/widgets/states.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import 'package:material_ui/material_ui.dart';

/// What the talent owes for a barter or hybrid stay: each deliverable, its due
/// date and status, handing it in (a post link or files, with the collaboration
/// label confirmed), and adding the post's numbers by hand.
class DeliverablesScreen extends ConsumerStatefulWidget {
  const new({required this.bookingId, super.key});

  final String bookingId;

  @override
  ConsumerState<DeliverablesScreen> createState() => _DeliverablesScreenState();
}

class _DeliverablesScreenState extends ConsumerState<DeliverablesScreen> {
  Future<List<Deliverable>>? _items;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  void _reload() => setState(() {
    _items = ref
        .read(deliverablesRepositoryProvider)
        .forBooking(widget.bookingId);
  });

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Deliverables')),
    body: FutureBuilder<List<Deliverable>>(
      future: _items,
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          final e = snapshot.error;
          return ErrorView(
            title: "We couldn't load your deliverables",
            message: e is ApiError ? e.userMessage : '$e',
            onRetry: _reload,
          );
        }
        final items = snapshot.data;
        if (items == null) return const LoadingView();
        if (items.isEmpty) {
          return const Center(
            child: Padding(
              padding: EdgeInsets.all(24),
              child: Text(
                'Nothing to hand in for this stay yet. Deliverables appear '
                "once you've checked in.",
                textAlign: TextAlign.center,
              ),
            ),
          );
        }
        return RefreshIndicator(
          onRefresh: () async => _reload(),
          child: ListView.separated(
            padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
            itemCount: items.length,
            separatorBuilder: (_, _) =>
                const SizedBox(height: BarterlySpace.md),
            itemBuilder: (context, i) =>
                _DeliverableCard(item: items[i], onChanged: _reload),
          ),
        );
      },
    ),
  );
}

String _count(int? n) =>
    n == null ? '–' : NumberFormat.decimalPattern('en_IN').format(n);

class _DeliverableCard extends StatelessWidget {
  const new({required this.item, required this.onChanged});

  final Deliverable item;
  final VoidCallback onChanged;

  @override
  Widget build(BuildContext context) {
    final latest = item.latest;
    return SurfaceCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        spacing: BarterlySpace.sm,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  item.title,
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ),
              Tag(label: item.status.label),
            ],
          ),
          Text('Due ${DateFormat('EEE d MMM').format(item.dueDate)}'),
          if (item.notes.isNotEmpty)
            Text(item.notes, style: Theme.of(context).textTheme.bodySmall),
          if (item.status == DeliverableStatus.changesRequested &&
              latest != null &&
              latest.reviewNote.isNotEmpty)
            Text(
              'Your host: ${latest.reviewNote}',
              style: const TextStyle(color: BarterlyColors.danger),
            ),
          for (final s in item.stats)
            Text(
              '${s.selfReported ? 'Self-reported' : 'From ${s.source}'}: '
              '${_count(s.views)} views · ${_count(s.likes)} likes · '
              '${_count(s.comments)} comments',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          Wrap(
            spacing: BarterlySpace.sm,
            children: [
              if (item.canSubmit)
                FilledButton(
                  onPressed: () async {
                    final done = await showModalBottomSheet<bool>(
                      context: context,
                      isScrollControlled: true,
                      builder: (_) => _SubmitSheet(item: item),
                    );
                    if (done ?? false) onChanged();
                  },
                  child: Text(
                    item.status == DeliverableStatus.pending
                        ? 'Hand in'
                        : 'Hand in again',
                  ),
                ),
              if (item.canReportStats)
                OutlinedButton(
                  onPressed: () async {
                    final done = await showModalBottomSheet<bool>(
                      context: context,
                      isScrollControlled: true,
                      builder: (_) => _StatsSheet(item: item),
                    );
                    if (done ?? false) onChanged();
                  },
                  child: const Text('Add your numbers'),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _SubmitSheet extends ConsumerStatefulWidget {
  const new({required this.item});

  final Deliverable item;

  @override
  ConsumerState<_SubmitSheet> createState() => _SubmitSheetState();
}

class _SubmitSheetState extends ConsumerState<_SubmitSheet> {
  late final _link = TextEditingController(
    text: widget.item.latest?.postUrl ?? '',
  );
  final _note = TextEditingController();
  final _files = <String>[];
  bool _labelled = false;
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _link.dispose();
    _note.dispose();
    super.dispose();
  }

  Future<void> _addFile(bool video) async {
    final picker = ref.read(mediaPickerProvider);
    final picked = video
        ? await picker.pickVideo(PickSource.gallery)
        : await picker.pickPhoto(PickSource.gallery);
    if (picked == null) return;
    setState(() => _busy = true);
    try {
      final bytes = await picker.read(picked.path);
      final id = await ref
          .read(mediaUploaderProvider)
          .upload(
            kind: video ? AttachmentKind.video : AttachmentKind.photo,
            contentType: picked.contentType,
            bytes: bytes,
          );
      setState(() => _files.add(id));
    } on ApiError catch (e) {
      setState(() => _error = e.userMessage);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _send() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref
          .read(deliverablesRepositoryProvider)
          .submit(
            widget.item.id,
            postUrl: _link.text.trim(),
            fileIds: _files,
            note: _note.text.trim(),
            disclosureConfirmed: _labelled,
          );
      if (mounted) Navigator.of(context).pop(true);
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
    final item = widget.item;
    final hasSomething = _link.text.trim().isNotEmpty || _files.isNotEmpty;
    final ready =
        hasSomething && (!item.disclosureRequired || _labelled) && !_busy;
    return Padding(
      padding: EdgeInsets.fromLTRB(
        20,
        20,
        20,
        20 + MediaQuery.viewInsetsOf(context).bottom,
      ),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          spacing: BarterlySpace.sm,
          children: [
            Text(
              'Hand in: ${item.title}',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            TextField(
              controller: _link,
              keyboardType: TextInputType.url,
              decoration: const InputDecoration(labelText: "The post's link"),
              onChanged: (_) => setState(() {}),
            ),
            Wrap(
              spacing: BarterlySpace.sm,
              children: [
                OutlinedButton.icon(
                  onPressed: _busy ? null : () => _addFile(false),
                  icon: const Icon(Icons.photo_outlined, size: 18),
                  label: const Text('Add photo'),
                ),
                OutlinedButton.icon(
                  onPressed: _busy ? null : () => _addFile(true),
                  icon: const Icon(Icons.videocam_outlined, size: 18),
                  label: const Text('Add video'),
                ),
              ],
            ),
            if (_files.isNotEmpty) Text('${_files.length} file(s) added'),
            TextField(
              controller: _note,
              maxLength: 500,
              decoration: const InputDecoration(
                labelText: 'Note for your host (optional)',
              ),
            ),
            if (item.disclosureRequired)
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                value: _labelled,
                onChanged: (v) => setState(() => _labelled = v ?? false),
                title: Text(
                  item.platform == 'google'
                      ? 'My review says I received a free stay for it'
                      : 'The post has the collaboration label (#collab or '
                            "#ad, or Instagram's paid partnership tag)",
                ),
                subtitle: const Text(
                  'Required by advertising rules (ASCI) for content made in '
                  'return for a stay.',
                ),
              ),
            if (_error != null)
              Text(
                _error!,
                style: const TextStyle(color: BarterlyColors.danger),
              ),
            FilledButton(
              onPressed: ready ? _send : null,
              child: Text(_busy ? 'Working…' : 'Hand in'),
            ),
          ],
        ),
      ),
    );
  }
}

class _StatsSheet extends ConsumerStatefulWidget {
  const new({required this.item});

  final Deliverable item;

  @override
  ConsumerState<_StatsSheet> createState() => _StatsSheetState();
}

class _StatsSheetState extends ConsumerState<_StatsSheet> {
  final _views = TextEditingController();
  final _likes = TextEditingController();
  final _comments = TextEditingController();
  String? _screenshot;
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _views.dispose();
    _likes.dispose();
    _comments.dispose();
    super.dispose();
  }

  Future<void> _pickScreenshot() async {
    final picker = ref.read(mediaPickerProvider);
    final picked = await picker.pickPhoto(PickSource.gallery);
    if (picked == null) return;
    setState(() => _busy = true);
    try {
      final id = await ref
          .read(mediaUploaderProvider)
          .upload(
            kind: AttachmentKind.photo,
            contentType: picked.contentType,
            bytes: await picker.read(picked.path),
          );
      setState(() => _screenshot = id);
    } on ApiError catch (e) {
      setState(() => _error = e.userMessage);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  int? _number(TextEditingController c) =>
      int.tryParse(c.text.replaceAll(RegExp('[^0-9]'), ''));

  Future<void> _send() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref
          .read(deliverablesRepositoryProvider)
          .reportStats(
            widget.item.id,
            screenshotId: _screenshot!,
            views: _number(_views),
            likes: _number(_likes),
            comments: _number(_comments),
          );
      if (mounted) Navigator.of(context).pop(true);
    } on ApiError catch (e) {
      if (mounted) {
        setState(() {
          _busy = false;
          _error = e.userMessage;
        });
      }
    }
  }

  Widget _field(String label, TextEditingController c) => TextField(
    controller: c,
    keyboardType: TextInputType.number,
    decoration: InputDecoration(labelText: label),
    onChanged: (_) => setState(() {}),
  );

  @override
  Widget build(BuildContext context) {
    final anyNumber = [
      _views,
      _likes,
      _comments,
    ].any((c) => _number(c) != null);
    return Padding(
      padding: EdgeInsets.fromLTRB(
        20,
        20,
        20,
        20 + MediaQuery.viewInsetsOf(context).bottom,
      ),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          spacing: BarterlySpace.sm,
          children: [
            Text(
              "Your post's numbers",
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const Text(
              'Your host sees these as self-reported, with your screenshot.',
            ),
            _field('Views', _views),
            _field('Likes', _likes),
            _field('Comments', _comments),
            OutlinedButton.icon(
              onPressed: _busy ? null : _pickScreenshot,
              icon: const Icon(Icons.screenshot_outlined, size: 18),
              label: Text(
                _screenshot == null ? 'Add a screenshot' : 'Screenshot added',
              ),
            ),
            if (_error != null)
              Text(
                _error!,
                style: const TextStyle(color: BarterlyColors.danger),
              ),
            FilledButton(
              onPressed: anyNumber && _screenshot != null && !_busy
                  ? _send
                  : null,
              child: const Text('Save numbers'),
            ),
          ],
        ),
      ),
    );
  }
}
