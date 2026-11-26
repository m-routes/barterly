import 'dart:async';

import 'package:barterly/src/agreements/agreement_models.dart';
import 'package:barterly/src/agreements/terms.dart';
import 'package:barterly/src/agreements/terms_view.dart';
import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/apply/outbox.dart' show myApplicationsProvider;
import 'package:barterly/src/discover/gig.dart' show shortDate;
import 'package:barterly/src/providers.dart';
import 'package:barterly/src/router.dart' show Routes;
import 'package:barterly/src/theme/tokens.dart';
import 'package:barterly/src/widgets/feedback.dart';
import 'package:barterly/src/widgets/states.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

/// The host's offer on one application: accept, decline, or ask for one change.
class OfferScreen extends ConsumerStatefulWidget {
  const new({required this.applicationId, super.key});

  final String applicationId;

  @override
  ConsumerState<OfferScreen> createState() => _OfferScreenState();
}

class _OfferScreenState extends ConsumerState<OfferScreen> {
  late Future<OfferThread> _thread = _load();
  bool _busy = false;

  Future<OfferThread> _load() =>
      ref.read(agreementsRepositoryProvider).offers(widget.applicationId);

  void _reload() => setState(() {
    _thread = _load();
  });

  void _show(String message) =>
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(message)));

  Future<void> _accept(Offer offer) async {
    final repository = ref.read(agreementsRepositoryProvider);
    setState(() => _busy = true);
    try {
      final bookingId = await repository.accept(offer.id);
      final agreement = await repository.agreementForBooking(bookingId);
      if (!mounted) return;
      _show('Accepted. The place is yours once you both sign.');
      ref.invalidate(myApplicationsProvider);
      context.pushReplacement(Routes.agreement(agreement.id));
    } on ApiError catch (error) {
      if (mounted) _show(error.userMessage);
      _reload();
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _decline(Offer offer) async {
    final reason = TextEditingController();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Decline this offer?'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('This ends your application for this gig.'),
            const SizedBox(height: BarterlySpace.md),
            TextField(
              controller: reason,
              maxLength: 500,
              decoration: const InputDecoration(
                labelText: 'Tell the host why (optional)',
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Keep it'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Decline'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() => _busy = true);
    try {
      await ref
          .read(agreementsRepositoryProvider)
          .decline(offer.id, reason: reason.text.trim());
      ref.invalidate(myApplicationsProvider);
      _reload();
    } on ApiError catch (error) {
      if (mounted) _show(error.userMessage);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _counter(Offer offer) async {
    final sent = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      builder: (_) => CounterSheet(offer: offer),
    );
    if (sent == true) {
      ref.invalidate(myApplicationsProvider);
      _reload();
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Offer')),
    body: FutureBuilder<OfferThread>(
      future: _thread,
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          final error = snapshot.error;
          return ErrorView(
            title: "We couldn't load the offer",
            message: error is ApiError ? error.userMessage : '$error',
            onRetry: _reload,
          );
        }
        final thread = snapshot.data;
        if (thread == null) return const LoadingView(label: 'Loading offer…');
        final offer = thread.current;
        if (offer == null) {
          return const EmptyState(
            icon: Icons.mail_outline,
            title: 'No offer yet',
            message: "When the host makes you an offer, you'll see it here.",
          );
        }
        return ListView(
          padding: const EdgeInsets.all(BarterlySpace.lg),
          children: [
            Text(
              _heading(offer, thread),
              style: Theme.of(context).textTheme.titleLarge,
            ),
            Padding(
              padding: const EdgeInsets.only(top: BarterlySpace.xs),
              child: Text(
                'Host: ${thread.hostReliability.label}',
                style: const TextStyle(color: BarterlyColors.inkMuted),
              ),
            ),
            if (offer.isHeld)
              Padding(
                padding: const EdgeInsets.only(top: BarterlySpace.sm),
                child: Text(_heldText(thread.expiresAt)),
              ),
            if (thread.expiresAt case final due? when offer.isOpen)
              Padding(
                padding: const EdgeInsets.only(top: BarterlySpace.xs),
                child: Text(
                  'Answer by ${shortDate(due.toLocal())}',
                  style: const TextStyle(color: BarterlyColors.inkMuted),
                ),
              ),
            if (offer.message.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: BarterlySpace.md),
                child: Text(
                  '“${offer.message}”',
                  style: const TextStyle(fontStyle: FontStyle.italic),
                ),
              ),
            const SizedBox(height: BarterlySpace.lg),
            SurfaceCard(
              child: TermsView(
                terms: offer.terms,
                changed: offer.changedFields,
              ),
            ),
            const SizedBox(height: BarterlySpace.lg),
            if (thread.yourTurn) ...[
              FilledButton(
                onPressed: _busy ? null : () => unawaited(_accept(offer)),
                child: Text(_busy ? 'Working…' : 'Accept and book'),
              ),
              if (thread.canCounter)
                OutlinedButton(
                  onPressed: _busy ? null : () => unawaited(_counter(offer)),
                  child: const Text('Ask for a change'),
                ),
              TextButton(
                onPressed: _busy ? null : () => unawaited(_decline(offer)),
                child: const Text('Decline'),
              ),
              if (!thread.canCounter && offer.isFinal)
                const Text(
                  'This is the final offer: you can accept or decline it.',
                  style: TextStyle(color: BarterlyColors.inkMuted),
                ),
            ] else if (offer.isOpen && offer.mine)
              const Text(
                'You asked for a change. The host will accept it or send back '
                'their original offer.',
              ),
            const SizedBox(height: BarterlySpace.md),
            const Text(
              'Accepting draws up an agreement you both sign; the place is '
              'yours once you both have. Its legal text is a placeholder '
              'still to be reviewed by a lawyer.',
              style: TextStyle(fontSize: 13, color: BarterlyColors.inkMuted),
            ),
          ],
        );
      },
    ),
  );

  String _heldText(DateTime? until) {
    const text =
        'Every place on this gig is taken for now. If one opens up before '
        "the stay, this offer opens again and we'll tell you.";
    if (until == null) return text;
    return '$text It lapses on ${shortDate(until.toLocal())}.';
  }

  String _heading(Offer offer, OfferThread thread) {
    if (offer.mine) return 'Your requested change';
    if (offer.status == 'accepted') return 'Offer accepted';
    if (offer.status == 'declined') return 'Offer declined';
    if (offer.isHeld) return 'Offer on hold';
    if (!offer.isOpen) return 'Offer closed';
    return offer.revision == 1
        ? 'The host made you an offer'
        : "The host's final offer";
  }
}

/// The one change the talent may ask for: dates, hours, stipend and
/// deliverables.
class CounterSheet extends ConsumerStatefulWidget {
  const new({required this.offer, super.key});

  final Offer offer;

  @override
  ConsumerState<CounterSheet> createState() => _CounterSheetState();
}

class _CounterSheetState extends ConsumerState<CounterSheet> {
  Terms get _base => widget.offer.terms;
  late DateTime _start = _base.startDate;
  late DateTime _end = _base.endDate;
  late int _hours = _base.hoursPerDay;
  late int _days = _base.daysPerWeek;
  late final _stipend = TextEditingController(text: _base.stipendAmount ?? '');
  late List<Deliverable> _deliverables = [..._base.deliverables];
  final _message = TextEditingController();
  bool _busy = false;
  String _error = '';

  Map<String, Object?> _changes() => {
    if (_start != _base.startDate) 'start_date': apiDate(_start),
    if (_end != _base.endDate) 'end_date': apiDate(_end),
    if (_hours != _base.hoursPerDay) 'hours_per_day': _hours,
    if (_days != _base.daysPerWeek) 'days_per_week': _days,
    if (_base.stipendAmount != null &&
        double.tryParse(_stipend.text) != double.tryParse(_base.stipendAmount!))
      'stipend_amount': _stipend.text.trim(),
    if (_deliverables.map((d) => d.quantity).join(',') !=
        _base.deliverables.map((d) => d.quantity).join(','))
      'deliverables': [for (final d in _deliverables) d.toJson()],
  };

  Future<void> _pick({required bool start}) async {
    final picked = await showDatePicker(
      context: context,
      initialDate: start ? _start : _end,
      firstDate: DateTime.now(),
      lastDate: DateTime.now().add(const Duration(days: 400)),
    );
    if (picked != null) setState(() => start ? _start = picked : _end = picked);
  }

  Future<void> _send() async {
    setState(() {
      _busy = true;
      _error = '';
    });
    try {
      await ref
          .read(agreementsRepositoryProvider)
          .counter(
            widget.offer.id,
            changes: _changes(),
            message: _message.text.trim(),
          );
      if (mounted) Navigator.pop(context, true);
    } on ApiError catch (error) {
      setState(() => _error = error.userMessage);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  void dispose() {
    _stipend.dispose();
    _message.dispose();
    super.dispose();
  }

  Widget _stepper(String label, int value, int max, ValueChanged<int> set) =>
      Row(
        children: [
          Expanded(child: Text(label)),
          IconButton(
            tooltip: 'Fewer $label',
            onPressed: value > 1 ? () => setState(() => set(value - 1)) : null,
            icon: const Icon(Icons.remove_circle_outline),
          ),
          Text('$value', key: Key('stepper-$label')),
          IconButton(
            tooltip: 'More $label',
            onPressed: value < max
                ? () => setState(() => set(value + 1))
                : null,
            icon: const Icon(Icons.add_circle_outline),
          ),
        ],
      );

  @override
  Widget build(BuildContext context) => Padding(
    padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
    child: SafeArea(
      child: ListView(
        shrinkWrap: true,
        padding: const EdgeInsets.all(BarterlySpace.lg),
        children: [
          Text(
            'Ask for a change',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: BarterlySpace.xs),
          const Text(
            'You can ask once. The host accepts your change (which books '
            'you) or sends back their original offer.',
            style: TextStyle(color: BarterlyColors.inkMuted),
          ),
          const SizedBox(height: BarterlySpace.md),
          ListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Arrive'),
            subtitle: Text(longDate(_start)),
            trailing: const Icon(Icons.edit_calendar_outlined),
            onTap: () => unawaited(_pick(start: true)),
          ),
          ListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Leave'),
            subtitle: Text(longDate(_end)),
            trailing: const Icon(Icons.edit_calendar_outlined),
            onTap: () => unawaited(_pick(start: false)),
          ),
          _stepper('hours a day', _hours, 6, (v) => _hours = v),
          _stepper('days a week', _days, 6, (v) => _days = v),
          if (_base.stipendAmount != null)
            TextField(
              controller: _stipend,
              keyboardType: const TextInputType.numberWithOptions(
                decimal: true,
              ),
              decoration: const InputDecoration(labelText: 'Stipend (₹)'),
              onChanged: (_) => setState(() {}),
            ),
          for (final (index, d) in _deliverables.indexed)
            _stepper(
              d.label,
              d.quantity,
              50,
              (v) => _deliverables = [
                for (final (i, item) in _deliverables.indexed)
                  if (i == index) item.withQuantity(v) else item,
              ],
            ),
          TextField(
            controller: _message,
            maxLength: 1000,
            decoration: const InputDecoration(
              labelText: 'Message to the host (optional)',
            ),
          ),
          if (_error.isNotEmpty)
            Text(_error, style: const TextStyle(color: BarterlyColors.danger)),
          const SizedBox(height: BarterlySpace.sm),
          FilledButton(
            onPressed: _busy || _changes().isEmpty
                ? null
                : () => unawaited(_send()),
            child: Text(_busy ? 'Sending…' : 'Send my change'),
          ),
        ],
      ),
    ),
  );
}
