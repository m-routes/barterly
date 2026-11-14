import 'dart:async';
import 'dart:math';

import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/apply/application.dart';
import 'package:barterly/src/apply/outbox.dart';
import 'package:barterly/src/discover/discover_controller.dart';
import 'package:barterly/src/discover/gig.dart';
import 'package:barterly/src/platform/media_picker.dart';
import 'package:barterly/src/providers.dart';
import 'package:barterly/src/theme/tokens.dart';
import 'package:barterly/src/widgets/feedback.dart';
import 'package:barterly/src/widgets/states.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

/// Size caps per kind (backend apps/media/policy.py).
const Map<AttachmentKind, int> _maxBytes = {
  AttachmentKind.photo: 10 * 1024 * 1024,
  AttachmentKind.video: 100 * 1024 * 1024,
  AttachmentKind.document: 10 * 1024 * 1024,
};

const agreementText =
    'I understand contact details unlock after both sides confirm, and I will '
    'sign the agreement before check-in.';

/// Apply to a gig (design canvas: TalentApply).
class ApplyScreen extends ConsumerWidget {
  const new({required this.gigId, super.key});

  final String gigId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final gig = ref.watch(gigProvider(gigId));
    return Scaffold(
      appBar: AppBar(title: const Text('Apply')),
      body: switch (gig) {
        AsyncData(:final value) => ApplyForm(gig: value),
        AsyncError(:final error) => ErrorView(
          title: "We couldn't open this gig",
          message: error is ApiError
              ? error.userMessage
              : 'Something went wrong. Try again.',
          onRetry: () => ref.invalidate(gigProvider(gigId)),
        ),
        _ => const SkeletonList(label: 'Loading the form', count: 2),
      },
    );
  }
}

class ApplyForm extends ConsumerStatefulWidget {
  const new({required this.gig, super.key});

  final Gig gig;

  @override
  ConsumerState<ApplyForm> createState() => _ApplyFormState();
}

class _ApplyFormState extends ConsumerState<ApplyForm> {
  final _form = GlobalKey<FormState>();
  final _pitch = TextEditingController();
  late final List<TextEditingController> _answers = [
    for (final _ in widget.gig.screeningQuestions ?? const <String>[])
      TextEditingController(),
  ];
  late DateTimeRange _dates = _defaultDates();
  List<AttachmentDraft> _attachments = [];
  bool _agreed = false;
  bool _showAgreementError = false;
  bool _sending = false;
  String? _progress;
  List<String> _problems = const [];

  /// Kept across retries so uploaded files aren't uploaded again.
  late final String _localId =
      '${DateTime.now().microsecondsSinceEpoch}-${Random().nextInt(1 << 32)}';

  @override
  void dispose() {
    _pitch.dispose();
    for (final c in _answers) {
      c.dispose();
    }
    super.dispose();
  }

  DateTime get _today {
    final now = DateTime.now();
    return DateTime(now.year, now.month, now.day);
  }

  DateTimeRange _defaultDates() {
    final gig = widget.gig;
    final tomorrow = _today.add(const Duration(days: 1));
    final start = gig.startDate == null || gig.startDate!.isBefore(tomorrow)
        ? tomorrow
        : gig.startDate!;
    var end = start.add(Duration(days: max(gig.minStayDays ?? 14, 1)));
    final last = gig.lastDay;
    if (last != null && end.isAfter(last) && last.isAfter(start)) end = last;
    return DateTimeRange(start: start, end: end);
  }

  Future<void> _pickDates() async {
    final gig = widget.gig;
    final first = gig.startDate != null && gig.startDate!.isAfter(_today)
        ? gig.startDate!
        : _today;
    final last = gig.lastDay ?? _today.add(const Duration(days: 365));
    if (!last.isAfter(first)) return;
    final range = await showDateRangePicker(
      context: context,
      firstDate: first,
      lastDate: last,
      initialDateRange: _dates.start.isBefore(first) || _dates.end.isAfter(last)
          ? null
          : _dates,
      helpText: 'Your dates',
    );
    if (range != null) setState(() => _dates = range);
  }

  // --- Attachments ---

  Future<void> _addFile(AttachmentKind kind) async {
    final source = await showModalBottomSheet<PickSource>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.photo_camera_outlined),
              title: Text(
                kind == AttachmentKind.video
                    ? 'Record a video'
                    : 'Take a photo',
              ),
              onTap: () => Navigator.pop(context, PickSource.camera),
            ),
            ListTile(
              leading: const Icon(Icons.photo_library_outlined),
              title: const Text('Choose from gallery'),
              onTap: () => Navigator.pop(context, PickSource.gallery),
            ),
          ],
        ),
      ),
    );
    if (source == null || !mounted) return;
    final picker = ref.read(mediaPickerProvider);
    final messenger = ScaffoldMessenger.of(context);
    try {
      final file = kind == AttachmentKind.video
          ? await picker.pickVideo(source)
          : await picker.pickPhoto(source);
      if (file == null || !mounted) return;
      final cap = _maxBytes[kind]!;
      if (file.sizeBytes > cap) {
        unawaited(picker.discard(file.path));
        messenger.showSnackBar(
          SnackBar(
            content: Text(
              'That file is too big. Keep it under ${cap ~/ (1024 * 1024)} MB.',
            ),
          ),
        );
        return;
      }
      setState(
        () => _attachments = [
          ..._attachments,
          AttachmentDraft(
            kind: kind,
            localPath: file.path,
            contentType: file.contentType,
            sizeBytes: file.sizeBytes,
            title: file.name,
          ),
        ],
      );
    } on UnsupportedFileType {
      messenger.showSnackBar(
        const SnackBar(
          content: Text('Use a JPEG, PNG or WebP photo, or an MP4 video.'),
        ),
      );
    } on Object {
      // Permission denied or the picker failed.
      messenger.showSnackBar(
        const SnackBar(
          content: Text(
            "We couldn't open your camera or photos. Check Barterly's "
            'permissions in Settings.',
          ),
        ),
      );
    }
  }

  Future<void> _addDocOrLink() async {
    final choice = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.link),
              title: const Text('Add a link'),
              subtitle: const Text('Portfolio, reel, CV (https only)'),
              onTap: () => Navigator.pop(context, 'link'),
            ),
            ListTile(
              leading: const Icon(Icons.description_outlined),
              title: const Text('Photo of a document'),
              subtitle: const Text('Certificate, reference letter'),
              onTap: () => Navigator.pop(context, 'document'),
            ),
          ],
        ),
      ),
    );
    if (!mounted) return;
    if (choice == 'document') return await _addFile(AttachmentKind.document);
    if (choice != 'link') return;
    final link = await showDialog<({String url, String title})>(
      context: context,
      builder: (_) => const _LinkDialog(),
    );
    if (link == null || !mounted) return;
    setState(
      () => _attachments = [
        ..._attachments,
        AttachmentDraft(
          kind: AttachmentKind.link,
          url: link.url,
          title: link.title,
        ),
      ],
    );
  }

  void _remove(int index) {
    final removed = _attachments[index];
    setState(() => _attachments = [..._attachments]..removeAt(index));
    if (removed.localPath != null) {
      unawaited(ref.read(mediaPickerProvider).discard(removed.localPath!));
    }
  }

  // --- Sending ---

  ApplicationDraft _draft() => ApplicationDraft(
    localId: _localId,
    gigId: widget.gig.id,
    gigTitle: widget.gig.title,
    place: widget.gig.property.place,
    pitch: _pitch.text,
    answers: [for (final c in _answers) c.text],
    proposedStart: _dates.start,
    proposedEnd: _dates.end,
    attachments: _attachments,
    createdAt: DateTime.now(),
  );

  Future<void> _submit() async {
    final valid = _form.currentState!.validate();
    setState(() => _showAgreementError = !_agreed);
    if (!valid || !_agreed || _sending) return;

    final draft = _draft();
    if (!await ref.read(networkStatusProvider).isOnline()) {
      await _queue(draft);
      return;
    }
    setState(() {
      _sending = true;
      _problems = const [];
    });
    final outcome = await ref
        .read(applicationSenderProvider)
        .send(
          draft,
          onProgress: (done, total) {
            if (!mounted || total == 0) return;
            setState(
              () => _progress = done < total
                  ? 'Uploading ${done + 1} of $total…'
                  : 'Sending…',
            );
          },
        );
    if (!mounted) return;
    setState(() {
      _sending = false;
      _progress = null;
      _attachments = outcome.draft.attachments;
    });
    switch (outcome) {
      case Sent():
        ref.invalidate(myApplicationsProvider);
        _done('Application sent. The host usually replies within a few days.');
      case Offline(:final draft):
        await _queue(draft);
      case final Refused refused:
        setState(() => _problems = refused.messages);
        await Scrollable.ensureVisible(
          _problemsKey.currentContext ?? context,
          duration: const Duration(milliseconds: 250),
        );
    }
  }

  final GlobalKey<State<StatefulWidget>> _problemsKey = GlobalKey();

  Future<void> _queue(ApplicationDraft draft) async {
    await ref.read(outboxProvider.notifier).enqueue(draft);
    if (!mounted) return;
    _done(
      "You're offline. Your application is saved and will send when "
      "you're back online.",
    );
  }

  void _done(String message) {
    final messenger = ScaffoldMessenger.of(context);
    final router = GoRouter.of(context);
    context.pop();
    messenger.showSnackBar(
      SnackBar(
        content: Text(message),
        action: SnackBarAction(
          label: 'My trips',
          onPressed: () => router.go('/trips'),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final gig = widget.gig;
    final theme = Theme.of(context);
    final questions = gig.screeningQuestions ?? const [];
    final colors = payModelColors(gig.payModel);
    final full = _attachments.length >= maxAttachments;
    return Form(
      key: _form,
      child: Column(
        children: [
          Expanded(
            child: ListView(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
              children: [
                SurfaceCard(
                  radius: 14,
                  child: Row(
                    spacing: 12,
                    children: [
                      Container(
                        width: 44,
                        height: 44,
                        decoration: BoxDecoration(
                          color: colors.tint,
                          borderRadius: BorderRadius.circular(12),
                        ),
                      ),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              gig.title,
                              style: const TextStyle(
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            Text(
                              [
                                gig.property.name,
                                ?gig.payModel?.label,
                              ].where((s) => s.isNotEmpty).join(' · '),
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
                if (_problems.isNotEmpty)
                  Padding(
                    key: _problemsKey,
                    padding: const EdgeInsets.only(top: 14),
                    child: _Problems(problems: _problems),
                  ),
                const SizedBox(height: 18),
                const _Label('Your dates'),
                const SizedBox(height: 6),
                OutlinedButton.icon(
                  onPressed: _sending ? null : _pickDates,
                  icon: const Icon(Icons.date_range_outlined),
                  label: Text(
                    '${shortDate(_dates.start)} to ${shortDate(_dates.end)} '
                    '(${_dates.duration.inDays} days)',
                  ),
                ),
                const SizedBox(height: 18),
                TextFormField(
                  controller: _pitch,
                  enabled: !_sending,
                  minLines: 4,
                  maxLines: 8,
                  maxLength: maxPitchLength,
                  textCapitalization: TextCapitalization.sentences,
                  decoration: const InputDecoration(
                    labelText: 'Your pitch',
                    hintText: 'Why you, and what you can bring to the property',
                    alignLabelWithHint: true,
                  ),
                  validator: (v) => (v ?? '').trim().isEmpty
                      ? 'Tell the host why you’re a good fit.'
                      : null,
                ),
                const SizedBox(height: 12),
                const _Label('Add proof of your work'),
                const SizedBox(height: 8),
                Row(
                  spacing: 8,
                  children: [
                    _AddButton(
                      icon: Icons.image_outlined,
                      label: 'Photos',
                      onTap: full || _sending
                          ? null
                          : () => _addFile(AttachmentKind.photo),
                    ),
                    _AddButton(
                      icon: Icons.videocam_outlined,
                      label: 'Intro video',
                      onTap: full || _sending
                          ? null
                          : () => _addFile(AttachmentKind.video),
                    ),
                    _AddButton(
                      icon: Icons.link,
                      label: 'Doc or link',
                      onTap: full || _sending ? null : _addDocOrLink,
                    ),
                  ],
                ),
                const SizedBox(height: 6),
                Text(
                  full
                      ? 'That’s the most you can add ($maxAttachments).'
                      : 'Up to $maxAttachments photos, videos, documents or '
                            'links.',
                  style: const TextStyle(
                    fontSize: 13,
                    color: BarterlyColors.inkMuted,
                  ),
                ),
                for (final (i, a) in _attachments.indexed)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: Icon(switch (a.kind) {
                      AttachmentKind.photo => Icons.image_outlined,
                      AttachmentKind.video => Icons.videocam_outlined,
                      AttachmentKind.document => Icons.description_outlined,
                      AttachmentKind.link => Icons.link,
                    }),
                    title: Text(
                      a.isLink ? (a.title.isEmpty ? a.url! : a.title) : a.title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    subtitle: Text(
                      a.isLink
                          ? a.url!
                          : '${a.kind.name[0].toUpperCase()}'
                                '${a.kind.name.substring(1)}'
                                '${a.mediaId != null ? ' · uploaded' : ''}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    trailing: IconButton(
                      tooltip: 'Remove',
                      onPressed: _sending ? null : () => _remove(i),
                      icon: const Icon(Icons.close),
                    ),
                  ),
                if (questions.isNotEmpty) ...[
                  const SizedBox(height: 18),
                  const _Label('Questions from the host'),
                  for (final (i, q) in questions.indexed)
                    Padding(
                      padding: const EdgeInsets.only(top: 12),
                      child: TextFormField(
                        controller: _answers[i],
                        enabled: !_sending,
                        maxLength: maxAnswerLength,
                        minLines: 1,
                        maxLines: 4,
                        decoration: InputDecoration(labelText: q),
                        validator: (v) => (v ?? '').trim().isEmpty
                            ? 'Answer this question.'
                            : null,
                      ),
                    ),
                ],
                const SizedBox(height: 18),
                MergeSemantics(
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Checkbox(
                        value: _agreed,
                        isError: _showAgreementError && !_agreed,
                        onChanged: _sending
                            ? null
                            : (v) => setState(() => _agreed = v ?? false),
                      ),
                      Expanded(
                        child: GestureDetector(
                          onTap: _sending
                              ? null
                              : () => setState(() => _agreed = !_agreed),
                          child: Padding(
                            padding: const EdgeInsets.only(top: 12),
                            child: Text(
                              agreementText,
                              style: theme.textTheme.bodyMedium?.copyWith(
                                height: 1.45,
                              ),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                if (_showAgreementError && !_agreed)
                  const Padding(
                    padding: EdgeInsets.only(left: 48),
                    child: Text(
                      'Tick this to send your application.',
                      style: TextStyle(color: BarterlyColors.danger),
                    ),
                  ),
              ],
            ),
          ),
          DecoratedBox(
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
                  onPressed: _sending ? null : _submit,
                  child: _sending
                      ? Row(
                          mainAxisSize: MainAxisSize.min,
                          spacing: 12,
                          children: [
                            const SizedBox.square(
                              dimension: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            ),
                            Text(_progress ?? 'Sending…'),
                          ],
                        )
                      : const Text('Send application'),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _Label extends StatelessWidget {
  const new(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Text(
    text,
    style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
  );
}

class _AddButton extends StatelessWidget {
  const new({required this.icon, required this.label, required this.onTap});

  final IconData icon;
  final String label;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) => Expanded(
    child: OutlinedButton(
      onPressed: onTap,
      style: OutlinedButton.styleFrom(
        minimumSize: const Size.fromHeight(72),
        padding: const EdgeInsets.symmetric(horizontal: 4),
        foregroundColor: BarterlyColors.ink,
        side: const BorderSide(color: BarterlyColors.fieldBorder),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        spacing: 4,
        children: [
          Icon(icon, size: 20),
          Text(label, style: const TextStyle(fontSize: 13)),
        ],
      ),
    ),
  );
}

class _Problems extends StatelessWidget {
  const new({required this.problems});

  final List<String> problems;

  @override
  Widget build(BuildContext context) => Semantics(
    liveRegion: true,
    child: Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: BarterlyColors.dangerSoft,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        spacing: 6,
        children: [
          const Text(
            "You can't apply yet",
            style: TextStyle(
              fontWeight: FontWeight.w600,
              color: BarterlyColors.danger,
            ),
          ),
          for (final p in problems)
            Text('• $p', style: const TextStyle(color: BarterlyColors.ink)),
        ],
      ),
    ),
  );
}

class _LinkDialog extends StatefulWidget {
  const new();

  @override
  State<_LinkDialog> createState() => _LinkDialogState();
}

class _LinkDialogState extends State<_LinkDialog> {
  final _form = GlobalKey<FormState>();
  final _url = TextEditingController();
  final _title = TextEditingController();

  @override
  void dispose() {
    _url.dispose();
    _title.dispose();
    super.dispose();
  }

  static String? validateLink(String? value) {
    final text = (value ?? '').trim();
    if (text.isEmpty) return 'Paste a link.';
    final uri = Uri.tryParse(text);
    if (uri == null || uri.scheme != 'https' || uri.host.isEmpty) {
      return 'Use an https:// link.';
    }
    if (text.length > 500) return 'That link is too long.';
    return null;
  }

  void _save() {
    if (!_form.currentState!.validate()) return;
    Navigator.pop(context, (url: _url.text.trim(), title: _title.text.trim()));
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Add a link'),
    content: Form(
      key: _form,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        spacing: 12,
        children: [
          TextFormField(
            controller: _url,
            autofocus: true,
            keyboardType: TextInputType.url,
            decoration: const InputDecoration(
              labelText: 'Link',
              hintText: 'https://',
            ),
            validator: validateLink,
          ),
          TextFormField(
            controller: _title,
            maxLength: 120,
            decoration: const InputDecoration(labelText: 'Title (optional)'),
          ),
        ],
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Cancel'),
      ),
      FilledButton(onPressed: _save, child: const Text('Add')),
    ],
  );
}
