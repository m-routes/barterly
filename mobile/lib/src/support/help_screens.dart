import 'package:barterly/src/analytics/analytics.dart';
import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/discover/gig.dart' show shortDate;
import 'package:barterly/src/providers.dart';
import 'package:barterly/src/support/support_models.dart';
import 'package:barterly/src/theme/tokens.dart';
import 'package:barterly/src/widgets/states.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show FutureProviderFamily;
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

final FutureProvider<List<SupportTicket>> myTicketsProvider =
    FutureProvider.autoDispose<List<SupportTicket>>(
      (ref) => ref.watch(supportRepositoryProvider).mine(),
    );

final FutureProviderFamily<SupportTicket, String> ticketProvider =
    FutureProvider.autoDispose.family<SupportTicket, String>(
      (ref, id) => ref.watch(supportRepositoryProvider).get(id),
    );

String _when(DateTime at) {
  final local = at.toLocal();
  String two(int n) => n.toString().padLeft(2, '0');
  final time = '${two(local.hour)}:${two(local.minute)}';
  return '${shortDate(local)}, $time';
}

/// Help and feedback: write to the Barterly team and see earlier requests.
class HelpScreen extends ConsumerWidget {
  const new({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tickets = ref.watch(myTicketsProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Help and feedback')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => context.push('/profile/help/new'),
        icon: const Icon(Icons.edit_outlined),
        label: const Text('Write to us'),
      ),
      body: RefreshIndicator(
        onRefresh: () => ref.refresh(myTicketsProvider.future),
        child: ListView(
          padding: const EdgeInsets.all(BarterlySpace.lg),
          children: [
            const Text(
              'We reply here and send you a notification. '
              'In an emergency, call 112.',
            ),
            const SizedBox(height: BarterlySpace.lg),
            ...switch (tickets) {
              AsyncData(:final value) when value.isEmpty => [
                const EmptyState(
                  icon: Icons.support_agent_outlined,
                  title: 'No requests yet',
                  message:
                      'Questions, problems and ideas you send appear here.',
                ),
              ],
              AsyncData(:final value) => [
                for (final ticket in value)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    title: Text(ticket.subject),
                    subtitle: Text(
                      '${ticket.reference} · ${ticket.statusLabel} · '
                      '${_when(ticket.lastMessageAt)}',
                    ),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => context.push('/profile/help/${ticket.id}'),
                  ),
              ],
              AsyncError(:final error) => [
                ErrorView(
                  title: "We couldn't load your requests",
                  message: error is ApiError ? error.userMessage : '$error',
                  onRetry: () => ref.invalidate(myTicketsProvider),
                ),
              ],
              _ => [const LoadingView(label: 'Loading your requests…')],
            },
          ],
        ),
      ),
    );
  }
}

/// The form: what it's about, a title and the message.
class NewRequestScreen extends ConsumerStatefulWidget {
  const new({this.bookingId, super.key});

  final String? bookingId;

  @override
  ConsumerState<NewRequestScreen> createState() => _NewRequestState();
}

class _NewRequestState extends ConsumerState<NewRequestScreen> {
  String? _kind;
  final _subject = TextEditingController();
  final _body = TextEditingController();
  bool _busy = false;
  String? _error;
  bool _tried = false;

  @override
  void dispose() {
    _subject.dispose();
    _body.dispose();
    super.dispose();
  }

  bool get _valid =>
      _kind != null &&
      _subject.text.trim().isNotEmpty &&
      _body.text.trim().isNotEmpty;

  Future<void> _send() async {
    setState(() => _tried = true);
    if (!_valid) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final ticket = await ref
          .read(supportRepositoryProvider)
          .open(
            kind: _kind!,
            subject: _subject.text.trim(),
            body: _body.text.trim(),
            bookingId: widget.bookingId,
            platform: platformName,
          );
      ref.read(analyticsProvider).track('feedback_sent', {'kind': _kind});
      ref.invalidate(myTicketsProvider);
      if (mounted) context.pushReplacement('/profile/help/${ticket.id}');
    } on ApiError catch (error) {
      if (mounted) setState(() => _error = error.userMessage);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final hint = [
      for (final (value, _, hint) in supportKinds)
        if (value == _kind) hint,
    ].firstOrNull;
    return Scaffold(
      appBar: AppBar(title: const Text('Write to us')),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(BarterlySpace.lg),
          children: [
            Text(
              "What's it about?",
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: BarterlySpace.sm),
            RadioGroup<String>(
              groupValue: _kind,
              onChanged: (value) => setState(() => _kind = value),
              child: Column(
                children: [
                  for (final (value, label, _) in supportKinds)
                    RadioListTile<String>(
                      contentPadding: EdgeInsets.zero,
                      value: value,
                      title: Text(label),
                    ),
                ],
              ),
            ),
            if (hint != null)
              Text(
                hint,
                style: const TextStyle(color: BarterlyColors.inkMuted),
              ),
            if (_tried && _kind == null)
              const Text(
                "Choose what it's about.",
                style: TextStyle(color: BarterlyColors.danger),
              ),
            const SizedBox(height: BarterlySpace.lg),
            TextField(
              controller: _subject,
              maxLength: 120,
              decoration: InputDecoration(
                labelText: 'Title',
                errorText: _tried && _subject.text.trim().isEmpty
                    ? 'Give it a short title.'
                    : null,
              ),
            ),
            const SizedBox(height: BarterlySpace.md),
            TextField(
              controller: _body,
              maxLength: 5000,
              minLines: 4,
              maxLines: 10,
              decoration: InputDecoration(
                labelText: 'Message',
                helperText: "Don't include card or bank details.",
                errorText: _tried && _body.text.trim().isEmpty
                    ? 'Tell us what happened.'
                    : null,
              ),
            ),
            if (_error != null) ...[
              const SizedBox(height: BarterlySpace.md),
              Text(
                _error!,
                style: const TextStyle(color: BarterlyColors.danger),
              ),
            ],
            const SizedBox(height: BarterlySpace.lg),
            FilledButton(
              onPressed: _busy ? null : _send,
              child: Text(_busy ? 'Sending…' : 'Send'),
            ),
          ],
        ),
      ),
    );
  }
}

/// One request: the conversation with support, and a box to write back.
class SupportThreadScreen extends ConsumerStatefulWidget {
  const new({required this.ticketId, super.key});

  final String ticketId;

  @override
  ConsumerState<SupportThreadScreen> createState() => _ThreadState();
}

class _ThreadState extends ConsumerState<SupportThreadScreen> {
  final _reply = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _reply.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final body = _reply.text.trim();
    if (body.isEmpty) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(supportRepositoryProvider).reply(widget.ticketId, body);
      _reply.clear();
      ref
        ..invalidate(ticketProvider(widget.ticketId))
        ..invalidate(myTicketsProvider);
    } on ApiError catch (error) {
      setState(() => _error = error.userMessage);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final ticket = ref.watch(ticketProvider(widget.ticketId));
    return Scaffold(
      appBar: AppBar(title: const Text('Your request')),
      body: switch (ticket) {
        AsyncData(:final value) => ListView(
          padding: const EdgeInsets.all(BarterlySpace.lg),
          children: [
            Text(value.subject, style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: BarterlySpace.xs),
            Text(
              [
                value.reference,
                value.statusLabel,
                if (value.replyExpectedBy != null)
                  'We aim to answer by ${_when(value.replyExpectedBy!)}',
              ].join(' · '),
              style: const TextStyle(color: BarterlyColors.inkMuted),
            ),
            const SizedBox(height: BarterlySpace.lg),
            for (final m in value.messages)
              Align(
                alignment: m.fromStaff
                    ? Alignment.centerRight
                    : Alignment.centerLeft,
                child: Container(
                  margin: const EdgeInsets.only(bottom: BarterlySpace.sm),
                  padding: const EdgeInsets.all(BarterlySpace.md),
                  constraints: const BoxConstraints(maxWidth: 480),
                  decoration: BoxDecoration(
                    color: m.fromStaff ? BarterlyColors.surfaceSunken : null,
                    border: Border.all(color: BarterlyColors.border),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '${m.fromStaff ? 'Barterly support' : 'You'} · '
                        '${_when(m.at)}',
                        style: const TextStyle(color: BarterlyColors.inkMuted),
                      ),
                      const SizedBox(height: BarterlySpace.xs),
                      SelectableText(m.body),
                    ],
                  ),
                ),
              ),
            const SizedBox(height: BarterlySpace.lg),
            TextField(
              controller: _reply,
              minLines: 2,
              maxLines: 6,
              maxLength: 5000,
              decoration: InputDecoration(
                labelText: value.status == 'resolved'
                    ? 'Still need help? Write back'
                    : 'Reply',
                errorText: _error,
              ),
            ),
            FilledButton(
              onPressed: _busy ? null : _send,
              child: Text(_busy ? 'Sending…' : 'Send'),
            ),
          ],
        ),
        AsyncError(:final error) => ErrorView(
          title: "We couldn't load this request",
          message: error is ApiError ? error.userMessage : '$error',
          onRetry: () => ref.invalidate(ticketProvider(widget.ticketId)),
        ),
        _ => const LoadingView(label: 'Loading your request…'),
      },
    );
  }
}
