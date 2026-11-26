import 'dart:async';

import 'package:barterly/src/agreements/agreement_models.dart';
import 'package:barterly/src/agreements/terms_view.dart';
import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/apply/outbox.dart' show myApplicationsProvider;
import 'package:barterly/src/auth/phone_auth.dart';
import 'package:barterly/src/auth/session.dart';
import 'package:barterly/src/discover/gig.dart' show shortDate;
import 'package:barterly/src/providers.dart';
import 'package:barterly/src/theme/tokens.dart';
import 'package:barterly/src/widgets/feedback.dart';
import 'package:barterly/src/widgets/states.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

/// A booking's agreement: every version, the PDF, and signing.
class AgreementScreen extends ConsumerStatefulWidget {
  const new({required this.agreementId, super.key});

  final String agreementId;

  @override
  ConsumerState<AgreementScreen> createState() => _AgreementScreenState();
}

class _AgreementScreenState extends ConsumerState<AgreementScreen> {
  late Future<Agreement> _agreement = _load();

  Future<Agreement> _load() =>
      ref.read(agreementsRepositoryProvider).agreement(widget.agreementId);

  void _reload() => setState(() {
    _agreement = _load();
  });

  void _show(String message) =>
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(message)));

  Future<void> _openPdf(AgreementVersion version) async {
    try {
      final url = await ref
          .read(agreementsRepositoryProvider)
          .pdfLink(version.id);
      await ref.read(urlOpenerProvider).openInApp(url);
    } on ApiError catch (error) {
      if (mounted) _show(error.userMessage);
    }
  }

  Future<void> _sign(AgreementVersion version) async {
    final signed = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      builder: (_) => SignSheet(version: version),
    );
    if (signed == true) {
      if (mounted) _show('Signed.');
      _reload();
    }
  }

  Future<void> _cancel(Agreement agreement) async {
    final cancelled = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      builder: (_) => CancelSheet(bookingId: agreement.bookingId),
    );
    if (cancelled == true) {
      if (mounted) _show('Booking cancelled.');
      ref.invalidate(myApplicationsProvider);
      _reload();
    }
  }

  Future<void> _declineChange(AgreementVersion version) async {
    try {
      await ref.read(agreementsRepositoryProvider).declineChange(version.id);
      _reload();
    } on ApiError catch (error) {
      if (mounted) _show(error.userMessage);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Agreement')),
    body: FutureBuilder<Agreement>(
      future: _agreement,
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          final error = snapshot.error;
          return ErrorView(
            title: "We couldn't load the agreement",
            message: error is ApiError ? error.userMessage : '$error',
            onRetry: _reload,
          );
        }
        final agreement = snapshot.data;
        if (agreement == null) {
          return const LoadingView(label: 'Loading agreement…');
        }
        return RefreshIndicator(
          onRefresh: () async => _reload(),
          child: ListView(
            padding: const EdgeInsets.all(BarterlySpace.lg),
            children: [
              Text(
                agreement.gigTitle,
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: BarterlySpace.xs),
              Tag(
                label: agreement.inForce
                    ? 'In force: version ${agreement.currentVersion}'
                    : 'Not signed by both yet',
                background: agreement.inForce
                    ? BarterlyColors.accentSoft
                    : BarterlyColors.surfaceSunken,
                foreground: agreement.inForce
                    ? BarterlyColors.onAccentSoft
                    : BarterlyColors.inkMuted,
              ),
              const SizedBox(height: BarterlySpace.sm),
              const Text(
                'Valid only once you and the host sign the same version. A '
                'change is a new version you both sign again.',
                style: TextStyle(color: BarterlyColors.inkMuted),
              ),
              const SizedBox(height: BarterlySpace.lg),
              BookingCard(
                agreement: agreement,
                onCancel: () => unawaited(_cancel(agreement)),
              ),
              for (final version in agreement.versions)
                Padding(
                  padding: const EdgeInsets.only(top: BarterlySpace.lg),
                  child: _VersionCard(
                    agreement: agreement,
                    version: version,
                    onOpenPdf: () => unawaited(_openPdf(version)),
                    onSign: () => unawaited(_sign(version)),
                    onDecline: () => unawaited(_declineChange(version)),
                  ),
                ),
            ],
          ),
        );
      },
    ),
  );
}

class _VersionCard extends StatelessWidget {
  const new({
    required this.agreement,
    required this.version,
    required this.onOpenPdf,
    required this.onSign,
    required this.onDecline,
  });

  final Agreement agreement;
  final AgreementVersion version;
  final VoidCallback onOpenPdf;
  final VoidCallback onSign;
  final VoidCallback onDecline;

  @override
  Widget build(BuildContext context) {
    final isChange =
        version.number > 1 && version.status == 'awaiting' && agreement.inForce;
    final mine = version.proposedBy == agreement.mySide;
    String side(String party) {
      final who = party == agreement.mySide
          ? 'You'
          : (party == 'vendor' ? 'Host' : 'Talent');
      final at = version.signedBy[party];
      final when = at == null
          ? 'not signed yet'
          : 'signed ${shortDate(at.toLocal())}';
      return '$who: $when';
    }

    return SurfaceCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        spacing: BarterlySpace.sm,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  'Version ${version.number}',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ),
              Tag(label: version.statusLabel, outlined: true),
            ],
          ),
          if (!version.templateReviewed)
            const Text(
              'The legal text is a placeholder that a lawyer must review '
              'before launch.',
              style: TextStyle(fontSize: 13, color: BarterlyColors.danger),
            ),
          if (version.changeReason.isNotEmpty)
            Text(
              '${mine ? 'You' : 'The host'} asked for this change: '
              '${version.changeReason}',
            ),
          TermsView(terms: version.terms, changed: version.changedFields),
          Text(side('vendor')),
          Text(side('talent')),
          Wrap(
            spacing: BarterlySpace.sm,
            children: [
              OutlinedButton.icon(
                onPressed: version.pdfReady ? onOpenPdf : null,
                icon: const Icon(Icons.picture_as_pdf_outlined, size: 18),
                label: Text(
                  version.pdfReady ? 'Open PDF' : 'PDF being prepared',
                ),
              ),
              if (isChange)
                TextButton(
                  onPressed: onDecline,
                  child: Text(
                    mine ? 'Withdraw this change' : 'Decline this change',
                  ),
                ),
            ],
          ),
          if (version.canSign)
            FilledButton(
              onPressed: onSign,
              child: Text('Sign version ${version.number}'),
            ),
        ],
      ),
    );
  }
}

/// Consent, a fresh OTP to the signer's own phone, then the signature.
class SignSheet extends ConsumerStatefulWidget {
  const new({required this.version, super.key});

  final AgreementVersion version;

  @override
  ConsumerState<SignSheet> createState() => _SignSheetState();
}

class _SignSheetState extends ConsumerState<SignSheet> {
  late final Future<SignChallenge> _challenge = ref
      .read(agreementsRepositoryProvider)
      .challenge(widget.version.id);
  bool _consent = false;
  bool _busy = false;
  String _error = '';
  Future<String> Function(String code)? _confirm;
  final _code = TextEditingController();

  String get _phone => switch (ref.read(sessionProvider)) {
    SignedIn(:final user) => user.phone,
    _ => '',
  };

  Future<void> _sendCode() async {
    setState(() {
      _busy = true;
      _error = '';
    });
    try {
      final verification = await ref.read(phoneAuthProvider).sendCode(_phone);
      switch (verification) {
        case CodeSent(:final confirm):
          setState(() => _confirm = confirm);
        case AutoVerified(:final idToken):
          // Android read the SMS itself: the phone is confirmed.
          await _finish(await _challenge, idToken);
      }
    } on PhoneAuthException catch (error) {
      setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _signWithCode(SignChallenge challenge) async {
    setState(() {
      _busy = true;
      _error = '';
    });
    try {
      final String token;
      if (challenge.needsOtp) {
        token = await _confirm!(_code.text.trim());
      } else {
        token = '';
      }
      await _finish(challenge, token);
    } on PhoneAuthException catch (error) {
      setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _finish(SignChallenge challenge, String token) async {
    try {
      await ref
          .read(agreementsRepositoryProvider)
          .sign(
            widget.version.id,
            documentSha256: challenge.documentSha256,
            otpToken: token,
          );
      if (token.isNotEmpty) unawaited(ref.read(phoneAuthProvider).signOut());
      if (mounted) Navigator.pop(context, true);
    } on ApiError catch (error) {
      setState(() {
        _error = error.userMessage;
        _confirm = null;
        _code.clear();
      });
    }
  }

  @override
  void dispose() {
    _code.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Padding(
    padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
    child: SafeArea(
      child: FutureBuilder<SignChallenge>(
        future: _challenge,
        builder: (context, snapshot) {
          if (snapshot.hasError) {
            final error = snapshot.error;
            return Padding(
              padding: const EdgeInsets.all(BarterlySpace.lg),
              child: Text(error is ApiError ? error.userMessage : '$error'),
            );
          }
          final challenge = snapshot.data;
          if (challenge == null) {
            return const SizedBox(height: 200, child: LoadingView());
          }
          final codeReady = RegExp(r'^\d{6}$').hasMatch(_code.text.trim());
          return ListView(
            shrinkWrap: true,
            padding: const EdgeInsets.all(BarterlySpace.lg),
            children: [
              Text(
                'Sign version ${widget.version.number}',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                controlAffinity: ListTileControlAffinity.leading,
                value: _consent,
                onChanged: (v) => setState(() => _consent = v ?? false),
                title: Text(challenge.consentText),
              ),
              if (challenge.needsOtp && _confirm == null)
                OutlinedButton(
                  onPressed: _consent && !_busy
                      ? () => unawaited(_sendCode())
                      : null,
                  child: Text('Send a code to ${challenge.phoneHint}'),
                ),
              if (challenge.needsOtp && _confirm != null)
                TextField(
                  controller: _code,
                  keyboardType: TextInputType.number,
                  maxLength: 6,
                  autofillHints: const [AutofillHints.oneTimeCode],
                  decoration: InputDecoration(
                    labelText: 'Code sent to ${challenge.phoneHint}',
                    helperText:
                        'Confirming your phone is part of your signature.',
                  ),
                  onChanged: (_) => setState(() {}),
                ),
              if (_error.isNotEmpty)
                Text(
                  _error,
                  style: const TextStyle(color: BarterlyColors.danger),
                ),
              const SizedBox(height: BarterlySpace.sm),
              FilledButton(
                onPressed:
                    _busy ||
                        !_consent ||
                        (challenge.needsOtp && (_confirm == null || !codeReady))
                    ? null
                    : () => unawaited(_signWithCode(challenge)),
                child: Text(_busy ? 'Signing…' : 'Sign'),
              ),
            ],
          );
        },
      ),
    ),
  );
}

const _unlockedWhile = {'confirmed', 'checked_in', 'delivering'};
const _cancellable = {'signing', 'confirmed'};

/// The booking behind the agreement: its status, what both signing unlocks
/// (the exact address, directions and the host's phone), and cancelling.
class BookingCard extends StatelessWidget {
  const new({required this.agreement, required this.onCancel, super.key});

  final Agreement agreement;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    final status = agreement.bookingStatus;
    return SurfaceCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        spacing: BarterlySpace.sm,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  'Your booking',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ),
              Tag(label: bookingStatusLabels[status] ?? status, outlined: true),
            ],
          ),
          if (status == 'signing')
            const Text(
              "The place is yours, and the exact address and host's phone "
              'are shared, once you both sign.',
              style: TextStyle(color: BarterlyColors.inkMuted),
            ),
          if (_unlockedWhile.contains(status))
            UnlockedDetailsView(bookingId: agreement.bookingId),
          if (_cancellable.contains(status))
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton(
                onPressed: onCancel,
                child: const Text('Cancel this booking'),
              ),
            ),
        ],
      ),
    );
  }
}

class UnlockedDetailsView extends ConsumerStatefulWidget {
  const new({required this.bookingId, super.key});

  final String bookingId;

  @override
  ConsumerState<UnlockedDetailsView> createState() =>
      _UnlockedDetailsViewState();
}

class _UnlockedDetailsViewState extends ConsumerState<UnlockedDetailsView> {
  late final Future<UnlockedDetails> _details = ref
      .read(agreementsRepositoryProvider)
      .details(widget.bookingId);

  void _open(Uri url) =>
      unawaited(ref.read(urlOpenerProvider).openExternal(url));

  @override
  Widget build(BuildContext context) => FutureBuilder<UnlockedDetails>(
    future: _details,
    builder: (context, snapshot) {
      if (snapshot.hasError) {
        final error = snapshot.error;
        return Text(error is ApiError ? error.userMessage : '$error');
      }
      final details = snapshot.data;
      if (details == null) return const LinearProgressIndicator();
      final place = details.place;
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        spacing: BarterlySpace.xs,
        children: [
          if (place != null) ...[
            Text(
              place.name,
              style: const TextStyle(fontWeight: FontWeight.w600),
            ),
            SelectableText(place.fullAddress),
            if (place.directions.isNotEmpty)
              Text('How to find it: ${place.directions}'),
            if (place.mapsUrl.isNotEmpty)
              OutlinedButton.icon(
                onPressed: () => _open(Uri.parse(place.mapsUrl)),
                icon: const Icon(Icons.directions_outlined, size: 18),
                label: const Text('Directions in Maps'),
              ),
          ],
          Text('Host: ${details.hostName}, ${details.hostPhone}'),
          OutlinedButton.icon(
            onPressed: () => _open(Uri(scheme: 'tel', path: details.hostPhone)),
            icon: const Icon(Icons.call_outlined, size: 18),
            label: const Text('Call the host'),
          ),
        ],
      );
    },
  );
}

/// Cancel before check-in: a reason from the list, after seeing what the
/// agreement's cancellation policy makes of it.
class CancelSheet extends ConsumerStatefulWidget {
  const new({required this.bookingId, super.key});

  final String bookingId;

  @override
  ConsumerState<CancelSheet> createState() => _CancelSheetState();
}

class _CancelSheetState extends ConsumerState<CancelSheet> {
  late final Future<CancelPreview> _preview = ref
      .read(agreementsRepositoryProvider)
      .cancelPreview(widget.bookingId);
  String? _reason;
  bool _busy = false;
  String _error = '';
  final _note = TextEditingController();

  @override
  void dispose() {
    _note.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() {
      _busy = true;
      _error = '';
    });
    try {
      await ref
          .read(agreementsRepositoryProvider)
          .cancel(widget.bookingId, reason: _reason!, note: _note.text.trim());
      if (mounted) Navigator.pop(context, true);
    } on ApiError catch (error) {
      setState(() => _error = error.userMessage);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Padding(
    padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
    child: SafeArea(
      child: FutureBuilder<CancelPreview>(
        future: _preview,
        builder: (context, snapshot) {
          if (snapshot.hasError) {
            final error = snapshot.error;
            return Padding(
              padding: const EdgeInsets.all(BarterlySpace.lg),
              child: Text(error is ApiError ? error.userMessage : '$error'),
            );
          }
          final preview = snapshot.data;
          if (preview == null) {
            return const SizedBox(height: 200, child: LoadingView());
          }
          final needsNote = _reason == 'other' && _note.text.trim().isEmpty;
          return ListView(
            shrinkWrap: true,
            padding: const EdgeInsets.all(BarterlySpace.lg),
            children: [
              Text(
                'Cancel this booking',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: BarterlySpace.sm),
              Text(
                preview.effectText,
                style: TextStyle(
                  color: preview.counts
                      ? BarterlyColors.danger
                      : BarterlyColors.inkMuted,
                ),
              ),
              if (preview.noticeDays case final notice?)
                Text(
                  "The agreement asks for $notice days' notice; the stay "
                  'starts in ${preview.daysBeforeStart} days.',
                  style: const TextStyle(color: BarterlyColors.inkMuted),
                ),
              const SizedBox(height: BarterlySpace.sm),
              RadioGroup<String>(
                groupValue: _reason,
                onChanged: (value) => setState(() => _reason = value),
                child: Column(
                  children: [
                    for (final (code, label) in preview.reasons)
                      RadioListTile<String>(
                        contentPadding: EdgeInsets.zero,
                        value: code,
                        title: Text(label),
                      ),
                  ],
                ),
              ),
              TextField(
                controller: _note,
                maxLength: 1000,
                decoration: InputDecoration(
                  labelText: _reason == 'other'
                      ? 'Say a little about why'
                      : 'More about why (optional)',
                ),
                onChanged: (_) => setState(() {}),
              ),
              if (_error.isNotEmpty)
                Text(
                  _error,
                  style: const TextStyle(color: BarterlyColors.danger),
                ),
              FilledButton(
                onPressed: _busy || _reason == null || needsNote
                    ? null
                    : () => unawaited(_submit()),
                child: Text(_busy ? 'Cancelling…' : 'Cancel the booking'),
              ),
              TextButton(
                onPressed: _busy ? null : () => Navigator.pop(context, false),
                child: const Text('Keep it'),
              ),
            ],
          );
        },
      ),
    ),
  );
}
