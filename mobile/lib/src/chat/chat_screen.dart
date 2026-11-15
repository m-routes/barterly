import 'dart:async';
import 'dart:math';

import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/apply/application.dart' show AttachmentKind;
import 'package:barterly/src/chat/chat_models.dart';
import 'package:barterly/src/chat/chat_transport.dart';
import 'package:barterly/src/platform/media_picker.dart';
import 'package:barterly/src/providers.dart';
import 'package:barterly/src/theme/tokens.dart';
import 'package:barterly/src/widgets/states.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import 'package:material_ui/material_ui.dart';

/// Mirrors backend apps/chat/services.py: photos up to 10 MB, 3 per message.
const Set<String> chatImageTypes = {'image/jpeg', 'image/png', 'image/webp'};
const int chatMaxBytes = 10 * 1024 * 1024;
const chatMaxAttachments = 3;

String newClientId() {
  final random = Random();
  return '${DateTime.now().microsecondsSinceEpoch}-${random.nextInt(1 << 32)}';
}

/// One conversation with a host. Polls (through [ChatTransport]) only while
/// this screen is open and the app is in the foreground.
class ChatScreen extends ConsumerStatefulWidget {
  const new({required this.conversationId, super.key});

  final String conversationId;

  @override
  ConsumerState<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends ConsumerState<ChatScreen>
    with WidgetsBindingObserver {
  late final ChatTransport _transport = ref.read(chatTransportProvider);
  Conversation? _conversation;
  Object? _error;
  List<ChatMessage> _messages = [];
  int _cursor = 0;
  int _readUpTo = 0;
  int _lastMarked = 0;
  bool _hasEarlier = false;
  bool _sending = false;
  String _notice = '';
  final List<PickedFile> _photos = [];
  final _text = TextEditingController();
  StreamSubscription<MessageBatch>? _live;

  String get _id => widget.conversationId;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    unawaited(_load());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    unawaited(_live?.cancel());
    _text.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _listen();
    } else if (state == AppLifecycleState.paused) {
      unawaited(_live?.cancel());
      _live = null;
    }
  }

  Future<void> _load() async {
    setState(() => _error = null);
    try {
      final repo = ref.read(chatRepositoryProvider);
      final conversation = await repo.conversation(_id);
      final page = await _transport.history(_id);
      if (!mounted) return;
      setState(() {
        _conversation = conversation;
        _apply(page);
        _hasEarlier = page.hasEarlier;
      });
      _listen();
    } on ApiError catch (error) {
      if (mounted) setState(() => _error = error);
    }
  }

  void _listen() {
    if (_live != null || _conversation == null) return;
    _live = _transport.watch(_id, _cursor).listen((batch) {
      if (mounted) setState(() => _apply(batch));
    }, onError: (_) {});
  }

  void _apply(MessageBatch batch) {
    _messages = mergeMessages(_messages, batch.messages);
    _cursor = max(_cursor, batch.cursor);
    _readUpTo = max(_readUpTo, batch.otherReadUpTo);
    final theirs = _messages.where((m) => !m.mine);
    if (theirs.isNotEmpty && theirs.last.cursor > _lastMarked) {
      _lastMarked = theirs.last.cursor;
      unawaited(_transport.markRead(_id, _lastMarked).catchError((_) {}));
    }
  }

  Future<void> _loadEarlier() async {
    if (_messages.isEmpty) return;
    final page = await _transport.history(_id, before: _messages.first.cursor);
    if (!mounted) return;
    setState(() {
      _messages = mergeMessages(_messages, page.messages);
      _hasEarlier = page.hasEarlier;
    });
  }

  Future<void> _pickPhoto() async {
    final messenger = ScaffoldMessenger.of(context);
    if (_photos.length >= chatMaxAttachments) {
      messenger.showSnackBar(
        const SnackBar(content: Text('Attach at most 3 photos.')),
      );
      return;
    }
    final file = await ref
        .read(mediaPickerProvider)
        .pickPhoto(PickSource.gallery);
    if (file == null || !mounted) return;
    final problem = !chatImageTypes.contains(file.contentType)
        ? 'Send a JPEG, PNG or WebP photo.'
        : file.sizeBytes > chatMaxBytes
        ? 'Photos can be up to 10 MB.'
        : null;
    if (problem != null) {
      messenger.showSnackBar(SnackBar(content: Text(problem)));
      return;
    }
    setState(() => _photos.add(file));
  }

  Future<void> _send() async {
    final body = _text.text.trim();
    if ((body.isEmpty && _photos.isEmpty) || _sending) return;
    final messenger = ScaffoldMessenger.of(context);
    setState(() {
      _sending = true;
      _notice = '';
    });
    try {
      final picker = ref.read(mediaPickerProvider);
      final uploader = ref.read(mediaUploaderProvider);
      final ids = <String>[];
      for (final photo in _photos) {
        ids.add(
          await uploader.upload(
            kind: AttachmentKind.photo,
            contentType: photo.contentType,
            bytes: await picker.read(photo.path),
          ),
        );
      }
      final result = await _transport.send(
        _id,
        body: body,
        clientId: newClientId(),
        attachmentIds: ids,
      );
      if (!mounted) return;
      setState(() {
        _messages = mergeMessages(_messages, [result.message]);
        _notice = result.notice;
        _text.clear();
        _photos.clear();
      });
    } on ApiError catch (error) {
      messenger.showSnackBar(SnackBar(content: Text(error.userMessage)));
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  Future<void> _toggleBlock() async {
    final c = _conversation!;
    if (!c.blockedByMe) {
      final yes = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text('Block ${c.otherName}?'),
          content: const Text(
            'Neither of you will be able to send messages. You can unblock '
            'them later.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Block'),
            ),
          ],
        ),
      );
      if (!(yes ?? false)) return;
    }
    if (!mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    try {
      final updated = await ref
          .read(chatRepositoryProvider)
          .setBlocked(_id, blocked: !c.blockedByMe);
      if (mounted) setState(() => _conversation = updated);
    } on ApiError catch (error) {
      messenger.showSnackBar(SnackBar(content: Text(error.userMessage)));
    }
  }

  Future<void> _report(ChatMessage message) async {
    final reason = await showModalBottomSheet<ReportReason>(
      context: context,
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const ListTile(title: Text('Why are you reporting this message?')),
            for (final r in ReportReason.values)
              ListTile(
                title: Text(r.label),
                onTap: () => Navigator.pop(context, r),
              ),
          ],
        ),
      ),
    );
    if (reason == null || !mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref.read(chatRepositoryProvider).report(message.id, reason);
      messenger.showSnackBar(
        const SnackBar(
          content: Text('Thanks. Our team will review this message.'),
        ),
      );
    } on ApiError catch (error) {
      messenger.showSnackBar(SnackBar(content: Text(error.userMessage)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = _conversation;
    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(c?.otherName ?? 'Chat'),
            if (c != null)
              Text(
                c.gigTitle,
                style: const TextStyle(
                  fontSize: 13,
                  color: BarterlyColors.inkMuted,
                ),
              ),
          ],
        ),
        actions: [
          if (c != null)
            PopupMenuButton<String>(
              onSelected: (_) => unawaited(_toggleBlock()),
              itemBuilder: (_) => [
                PopupMenuItem(
                  value: 'block',
                  child: Text(c.blockedByMe ? 'Unblock' : 'Block'),
                ),
              ],
            ),
        ],
      ),
      body: switch ((c, _error)) {
        (_, final ApiError error) => ErrorView(
          title: "We couldn't load this chat",
          message: error.userMessage,
          onRetry: _load,
        ),
        (null, _) => const LoadingView(label: 'Loading the chat…'),
        (final Conversation c, _) => _body(c),
      },
    );
  }

  Widget _body(Conversation c) => Column(
    children: [
      if (!c.contactSharingAllowed)
        Container(
          width: double.infinity,
          color: BarterlyColors.surfaceSunken,
          padding: const EdgeInsets.all(12),
          child: const Text(
            'Phone numbers, emails and links are hidden until the booking is '
            "confirmed. Keep the conversation on Barterly so you're covered.",
            style: TextStyle(fontSize: 13),
          ),
        ),
      Expanded(
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (_hasEarlier)
              TextButton(
                onPressed: _loadEarlier,
                child: const Text('Load earlier messages'),
              ),
            if (_messages.isEmpty)
              const Padding(
                padding: EdgeInsets.all(24),
                child: Text(
                  'No messages yet.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: BarterlyColors.inkMuted),
                ),
              ),
            for (final m in _messages)
              _Bubble(
                message: m,
                seen: m.mine && m.cursor <= _readUpTo,
                onReport: m.mine ? null : () => unawaited(_report(m)),
              ),
          ],
        ),
      ),
      if (_notice.isNotEmpty)
        Container(
          width: double.infinity,
          color: BarterlyColors.dangerSoft,
          padding: const EdgeInsets.all(12),
          child: Text(_notice, key: const Key('chat-notice')),
        ),
      SafeArea(
        top: false,
        child: c.canSend
            ? _composer()
            : Padding(
                padding: const EdgeInsets.all(16),
                child: Text(
                  c.cantSendReason,
                  style: const TextStyle(color: BarterlyColors.inkMuted),
                ),
              ),
      ),
    ],
  );

  Widget _composer() => Padding(
    padding: const EdgeInsets.fromLTRB(8, 4, 8, 8),
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (_photos.isNotEmpty)
          Row(
            children: [
              Expanded(
                child: Text(
                  '${_photos.length} photo${_photos.length == 1 ? '' : 's'} '
                  'attached',
                ),
              ),
              TextButton(
                onPressed: () => setState(_photos.clear),
                child: const Text('Remove'),
              ),
            ],
          ),
        Row(
          children: [
            IconButton(
              tooltip: 'Attach a photo',
              onPressed: _sending ? null : _pickPhoto,
              icon: const Icon(Icons.photo_outlined),
            ),
            Expanded(
              child: TextField(
                controller: _text,
                minLines: 1,
                maxLines: 4,
                maxLength: 2000,
                decoration: const InputDecoration(
                  hintText: 'Message',
                  counterText: '',
                ),
              ),
            ),
            IconButton(
              tooltip: 'Send',
              onPressed: _sending ? null : _send,
              icon: const Icon(Icons.send),
            ),
          ],
        ),
      ],
    ),
  );
}

class _Bubble extends StatelessWidget {
  const new({required this.message, required this.seen, this.onReport});

  final ChatMessage message;
  final bool seen;
  final VoidCallback? onReport;

  @override
  Widget build(BuildContext context) {
    final m = message;
    final time = DateFormat('d MMM, h:mm a').format(m.createdAt.toLocal());
    return Align(
      alignment: m.mine ? Alignment.centerRight : Alignment.centerLeft,
      child: GestureDetector(
        onLongPress: onReport,
        child: Container(
          margin: const EdgeInsets.only(bottom: 10),
          constraints: const BoxConstraints(maxWidth: 300),
          child: Column(
            crossAxisAlignment: m.mine
                ? CrossAxisAlignment.end
                : CrossAxisAlignment.start,
            children: [
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 8,
                ),
                decoration: BoxDecoration(
                  color: m.mine
                      ? BarterlyColors.accentSoft
                      : BarterlyColors.surfaceSunken,
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (m.body.isNotEmpty) Text(m.body),
                    for (final a in m.attachments)
                      Text(
                        a.isImage ? 'Photo' : 'PDF',
                        style: const TextStyle(
                          decoration: TextDecoration.underline,
                        ),
                      ),
                  ],
                ),
              ),
              Text(
                [
                  time,
                  if (m.masked) 'contact details hidden',
                  if (seen) 'Seen',
                ].join(' · '),
                style: const TextStyle(
                  fontSize: 12,
                  color: BarterlyColors.inkMuted,
                ),
              ),
              if (onReport != null)
                TextButton(onPressed: onReport, child: const Text('Report')),
            ],
          ),
        ),
      ),
    );
  }
}
