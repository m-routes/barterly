import 'dart:async';

import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/providers.dart';
import 'package:barterly/src/theme/tokens.dart';
import 'package:barterly/src/wallet/wallet_models.dart';
import 'package:barterly/src/widgets/feedback.dart';
import 'package:barterly/src/widgets/states.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import 'package:material_ui/material_ui.dart';

/// The Wallet tab: what's held for you, what's yours to pay out, where payouts
/// go, and everything released and paid so far.
class WalletScreen extends ConsumerStatefulWidget {
  const new({super.key});

  @override
  ConsumerState<WalletScreen> createState() => _WalletScreenState();
}

class _WalletScreenState extends ConsumerState<WalletScreen> {
  Future<Wallet>? _wallet;
  final _history = <WalletEntry>[];
  String _kind = '';
  int _page = 1;
  bool _hasMore = false;
  bool _loadingHistory = false;
  bool _paying = false;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  void _reload() {
    setState(() {
      _wallet = ref.read(walletRepositoryProvider).wallet();
    });
    unawaited(_loadHistory(reset: true));
  }

  Future<void> _loadHistory({bool reset = false}) async {
    if (_loadingHistory) return;
    setState(() {
      _loadingHistory = true;
      if (reset) {
        _page = 1;
        _history.clear();
      }
    });
    try {
      final page = await ref
          .read(walletRepositoryProvider)
          .history(kind: _kind, page: _page);
      if (!mounted) return;
      setState(() {
        _history.addAll(page.entries);
        _hasMore = page.hasMore;
        _page += 1;
      });
    } on ApiError {
      // The balances still show; the list says it couldn't load.
    } finally {
      if (mounted) setState(() => _loadingHistory = false);
    }
  }

  Future<void> _payOut() async {
    final messenger = ScaffoldMessenger.of(context);
    setState(() => _paying = true);
    try {
      final (sent, held) = await ref
          .read(walletRepositoryProvider)
          .requestPayout();
      messenger.showSnackBar(
        SnackBar(
          content: Text(
            sent > 0
                ? 'Payout on its way.'
                : held.isNotEmpty
                ? "Payouts are on hold. We'll pay as soon as we can."
                : 'Nothing to pay out right now.',
          ),
        ),
      );
      _reload();
    } on ApiError catch (e) {
      messenger.showSnackBar(SnackBar(content: Text(e.userMessage)));
    } finally {
      if (mounted) setState(() => _paying = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Wallet')),
    body: FutureBuilder<Wallet>(
      future: _wallet,
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          final e = snapshot.error;
          return ErrorView(
            title: "We couldn't load your wallet",
            message: e is ApiError ? e.userMessage : '$e',
            onRetry: _reload,
          );
        }
        final wallet = snapshot.data;
        if (wallet == null) return const LoadingView(label: 'Loading wallet…');
        return RefreshIndicator(
          onRefresh: () async => _reload(),
          child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
            children: [
              _Balances(wallet: wallet),
              if (wallet.holdMessage.isNotEmpty) ...[
                const SizedBox(height: BarterlySpace.sm),
                SurfaceCard(
                  color: BarterlyColors.surfaceSunken,
                  child: Row(
                    spacing: BarterlySpace.sm,
                    children: [
                      const Icon(Icons.info_outline),
                      Expanded(child: Text(wallet.holdMessage)),
                    ],
                  ),
                ),
              ],
              const SizedBox(height: BarterlySpace.sm),
              FilledButton(
                onPressed: wallet.canRequestPayout && !_paying ? _payOut : null,
                child: Text(
                  _paying
                      ? 'Sending…'
                      : 'Pay out ${rupees(wallet.available)} now',
                ),
              ),
              const SizedBox(height: BarterlySpace.md),
              _AccountCard(account: wallet.account, onChanged: _reload),
              const SizedBox(height: BarterlySpace.lg),
              Text('History', style: Theme.of(context).textTheme.titleMedium),
              Wrap(
                spacing: BarterlySpace.xs,
                children: [
                  for (final (kind, label) in const [
                    ('', 'All'),
                    ('release', 'Released'),
                    ('payout', 'Payouts'),
                  ])
                    ChoiceChip(
                      label: Text(label),
                      selected: _kind == kind,
                      onSelected: (_) {
                        _kind = kind;
                        unawaited(_loadHistory(reset: true));
                      },
                    ),
                ],
              ),
              if (_history.isEmpty && !_loadingHistory)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: BarterlySpace.md),
                  child: Text('Nothing here yet.'),
                ),
              for (final entry in _history) _EntryTile(entry: entry),
              if (_hasMore)
                TextButton(
                  onPressed: _loadingHistory ? null : _loadHistory,
                  child: const Text('Show more'),
                ),
            ],
          ),
        );
      },
    ),
  );
}

class _Balances extends StatelessWidget {
  const new({required this.wallet});

  final Wallet wallet;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    Widget line(String label, int paise, {String? hint}) => Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label),
                if (hint != null) Text(hint, style: theme.textTheme.bodySmall),
              ],
            ),
          ),
          Text(rupees(paise), style: theme.textTheme.titleMedium),
        ],
      ),
    );
    return SurfaceCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        spacing: BarterlySpace.xs,
        children: [
          Text('Available', style: theme.textTheme.bodyMedium),
          Text(rupees(wallet.available), style: theme.textTheme.headlineMedium),
          const Divider(),
          line(
            'Held in escrow',
            wallet.pending,
            hint:
                'About ${rupees(wallet.pendingNetEstimate)} to you after '
                'commission, GST and TDS',
          ),
          line('On its way', wallet.inTransit),
          line('Paid out', wallet.paidOut),
          line('TDS deducted, FY ${wallet.financialYear}', wallet.tdsThisYear),
        ],
      ),
    );
  }
}

class _AccountCard extends StatelessWidget {
  const new({required this.account, required this.onChanged});

  final PayoutAccount? account;
  final VoidCallback onChanged;

  @override
  Widget build(BuildContext context) {
    final a = account;
    return SurfaceCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        spacing: BarterlySpace.xs,
        children: [
          Text(
            'Payout account',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          if (a == null)
            const Text('Add a UPI id or bank account to get paid.')
          else ...[
            Row(
              children: [
                Expanded(child: Text(a.display)),
                Tag(label: a.statusLabel),
              ],
            ),
            if (a.failed && a.reason.isNotEmpty)
              Text(
                a.reason,
                style: const TextStyle(color: BarterlyColors.danger),
              ),
            if (a.holdUntil case final until?
                when until.isAfter(DateTime.now()))
              Text(
                'Changed recently: payouts wait until '
                '${DateFormat('d MMM, h:mm a').format(until.toLocal())}.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
          ],
          OutlinedButton(
            onPressed: () async {
              final linked = await Navigator.of(context).push<bool>(
                MaterialPageRoute(
                  builder: (_) => LinkAccountScreen(replacing: a != null),
                ),
              );
              if (linked ?? false) onChanged();
            },
            child: Text(a == null ? 'Add payout account' : 'Change account'),
          ),
        ],
      ),
    );
  }
}

class _EntryTile extends StatelessWidget {
  const new({required this.entry});

  final WalletEntry entry;

  @override
  Widget build(BuildContext context) {
    final isPayout = entry.kind == 'payout';
    final detail = isPayout
        ? [
            entry.statusLabel,
            if (entry.account.isNotEmpty) 'to ${entry.account}',
            if (entry.failureReason.isNotEmpty) entry.failureReason,
          ]
        : [
            '${rupees(entry.gross)} released',
            '− ${rupees(entry.fees)} commission and GST',
            if (entry.tds > 0) '− ${rupees(entry.tds)} TDS',
          ];
    return ListTile(
      contentPadding: EdgeInsets.zero,
      leading: Icon(isPayout ? Icons.north_east : Icons.lock_open_outlined),
      title: Text(isPayout ? 'Payout' : entry.gigTitle),
      subtitle: Text(
        '${DateFormat('d MMM y').format(entry.at.toLocal())} · '
        '${detail.join(' · ')}',
      ),
      trailing: Text(rupees(entry.amount)),
    );
  }
}

/// Adding or changing where payouts go: a UPI id, or a bank account. The
/// details go straight to the payout provider; Barterly keeps a masked
/// version only.
class LinkAccountScreen extends ConsumerStatefulWidget {
  const new({required this.replacing, super.key});

  final bool replacing;

  @override
  ConsumerState<LinkAccountScreen> createState() => _LinkAccountScreenState();
}

const _checkNote =
    'We send ₹1 to check the account before paying into it. Only a masked '
    'version is kept.';
const _holdNote =
    "For your safety, payouts wait 24 hours after a change, and we'll let "
    'you know by SMS and email.';

class _LinkAccountScreenState extends ConsumerState<LinkAccountScreen> {
  final _form = GlobalKey<FormState>();
  String _method = 'upi';
  final _vpa = TextEditingController();
  final _account = TextEditingController();
  final _ifsc = TextEditingController();
  final _name = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    for (final c in [_vpa, _account, _ifsc, _name]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _save() async {
    if (!_form.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    final repo = ref.read(walletRepositoryProvider);
    try {
      await (_method == 'upi'
          ? repo.linkUpi(_vpa.text)
          : repo.linkBank(
              accountNumber: _account.text,
              ifsc: _ifsc.text,
              holderName: _name.text,
            ));
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
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: Text(
        widget.replacing ? 'Change payout account' : 'Add payout account',
      ),
    ),
    body: Form(
      key: _form,
      child: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          SegmentedButton<String>(
            segments: const [
              ButtonSegment(value: 'upi', label: Text('UPI')),
              ButtonSegment(value: 'bank', label: Text('Bank account')),
            ],
            selected: {_method},
            onSelectionChanged: (s) => setState(() => _method = s.first),
          ),
          const SizedBox(height: BarterlySpace.md),
          if (_method == 'upi')
            TextFormField(
              controller: _vpa,
              keyboardType: TextInputType.emailAddress,
              autocorrect: false,
              decoration: const InputDecoration(
                labelText: 'UPI id',
                hintText: 'name@bank',
              ),
              validator: (v) => PayoutDetails.checkVpa(v ?? ''),
            )
          else ...[
            TextFormField(
              controller: _name,
              decoration: const InputDecoration(
                labelText: 'Name on the account',
              ),
              validator: (v) => PayoutDetails.checkName(v ?? ''),
            ),
            TextFormField(
              controller: _account,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: 'Account number'),
              validator: (v) => PayoutDetails.checkAccount(v ?? ''),
            ),
            TextFormField(
              controller: _ifsc,
              textCapitalization: TextCapitalization.characters,
              decoration: const InputDecoration(labelText: 'IFSC code'),
              validator: (v) => PayoutDetails.checkIfsc(v ?? ''),
            ),
          ],
          const SizedBox(height: BarterlySpace.md),
          Text(
            widget.replacing ? '$_checkNote $_holdNote' : _checkNote,
            style: Theme.of(context).textTheme.bodySmall,
          ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: BarterlySpace.sm),
              child: Text(
                _error!,
                style: const TextStyle(color: BarterlyColors.danger),
              ),
            ),
          const SizedBox(height: BarterlySpace.md),
          FilledButton(
            onPressed: _busy ? null : _save,
            child: Text(_busy ? 'Checking…' : 'Save'),
          ),
        ],
      ),
    ),
  );
}
