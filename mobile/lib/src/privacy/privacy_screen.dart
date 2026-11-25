import 'package:barterly/src/analytics/analytics.dart';
import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/discover/gig.dart' show shortDate;
import 'package:barterly/src/privacy/legal.dart';
import 'package:barterly/src/privacy/legal_links.dart';
import 'package:barterly/src/privacy/privacy_models.dart';
import 'package:barterly/src/providers.dart';
import 'package:barterly/src/theme/tokens.dart';
import 'package:barterly/src/widgets/states.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

final FutureProvider<List<Consent>> consentsProvider =
    FutureProvider.autoDispose<List<Consent>>(
      (ref) => ref.watch(privacyRepositoryProvider).consents(),
    );

final FutureProvider<DeletionState> deletionProvider =
    FutureProvider.autoDispose<DeletionState>(
      (ref) => ref.watch(privacyRepositoryProvider).deletion(),
    );

const _purposeText = {
  'location':
      'Record where you are when you open your check-in pass. Check-in '
      'works without it.',
  'social': 'Read public numbers for posts you hand in, and check your handle.',
  'marketing':
      "Offers and news. Booking and payment messages aren't marketing.",
  'analytics':
      "Count which screens and steps you use, so we can fix what's "
      "confusing. Never your messages, location or contacts; you're a random "
      'code, not a name. Withdrawing deletes what we have.',
};

/// Consents, a copy of your data, corrections and deleting the account. Every
/// consent is one switch: withdrawing is as easy as giving.
class PrivacyScreen extends ConsumerWidget {
  const new({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Privacy and your data')),
      body: ListView(
        padding: const EdgeInsets.all(BarterlySpace.lg),
        children: [
          Text('Your consents', style: theme.textTheme.titleLarge),
          const _Consents(),
          const Divider(height: BarterlySpace.xl * 2),
          Text('Your data', style: theme.textTheme.titleLarge),
          const SizedBox(height: BarterlySpace.sm),
          const _ExportButton(),
          const SizedBox(height: BarterlySpace.sm),
          OutlinedButton(
            onPressed: () => _askCorrection(context, ref),
            child: const Text('Ask for a correction'),
          ),
          const Divider(height: BarterlySpace.xl * 2),
          Text('Delete your account', style: theme.textTheme.titleLarge),
          const SizedBox(height: BarterlySpace.sm),
          const _Deletion(),
          const Divider(height: BarterlySpace.xl * 2),
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.policy_outlined),
            title: const Text('Privacy policy'),
            trailing: const Icon(Icons.open_in_new),
            onTap: () => openLegalPage(ref, LegalPaths.privacy),
          ),
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.support_agent_outlined),
            title: const Text('Grievance Officer'),
            subtitle: const Text('Complaints about your data or the app'),
            trailing: const Icon(Icons.open_in_new),
            onTap: () => openLegalPage(ref, LegalPaths.grievance),
          ),
        ],
      ),
    );
  }

  Future<void> _askCorrection(BuildContext context, WidgetRef ref) async {
    final messenger = ScaffoldMessenger.of(context);
    final answer = await showDialog<({String field, String value})>(
      context: context,
      builder: (_) => const _CorrectionDialog(),
    );
    if (answer == null) return;
    try {
      await ref
          .read(privacyRepositoryProvider)
          .requestCorrection(field: answer.field, correctValue: answer.value);
      messenger.showSnackBar(
        const SnackBar(content: Text("Sent. We'll get back to you.")),
      );
    } on ApiError catch (error) {
      messenger.showSnackBar(SnackBar(content: Text(error.userMessage)));
    }
  }
}

class _Consents extends ConsumerWidget {
  const new();

  @override
  Widget build(BuildContext context, WidgetRef ref) =>
      switch (ref.watch(consentsProvider)) {
        AsyncData(:final value) => Column(
          children: [
            for (final consent in value)
              if (consent.required)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(consent.label),
                  subtitle: Text(
                    consent.granted
                        ? 'Accepted (version ${consent.version}). Needed to '
                              'use Barterly; delete your account to withdraw.'
                        : 'Not accepted',
                  ),
                )
              else
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(consent.label),
                  subtitle: Text(_purposeText[consent.purpose] ?? ''),
                  value: consent.granted,
                  onChanged: (granted) => _set(context, ref, consent, granted),
                ),
          ],
        ),
        AsyncError(:final error) => ErrorView(
          message: error is ApiError ? error.userMessage : '$error',
          onRetry: () => ref.invalidate(consentsProvider),
        ),
        _ => const LoadingView(label: 'Loading your consents…'),
      };

  Future<void> _set(
    BuildContext context,
    WidgetRef ref,
    Consent consent,
    bool granted,
  ) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref
          .read(privacyRepositoryProvider)
          .setConsent(consent.purpose, granted: granted);
      if (consent.purpose == 'analytics') {
        ref.read(analyticsProvider).setConsent(granted: granted);
      }
      ref.invalidate(consentsProvider);
      messenger.showSnackBar(
        SnackBar(
          content: Text(
            granted
                ? '${consent.label}: allowed.'
                : '${consent.label}: withdrawn.',
          ),
        ),
      );
    } on ApiError catch (error) {
      messenger.showSnackBar(SnackBar(content: Text(error.userMessage)));
    }
  }
}

class _ExportButton extends ConsumerStatefulWidget {
  const new();

  @override
  ConsumerState<_ExportButton> createState() => _ExportState();
}

class _ExportState extends ConsumerState<_ExportButton> {
  bool _busy = false;

  Future<void> _export() async {
    final messenger = ScaffoldMessenger.of(context);
    setState(() => _busy = true);
    try {
      final privacy = ref.read(privacyRepositoryProvider);
      final export = await privacy.createExport();
      final url = await privacy.exportLink(export.id);
      await ref.read(urlOpenerProvider).openExternal(url);
    } on ApiError catch (error) {
      messenger.showSnackBar(SnackBar(content: Text(error.userMessage)));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => FilledButton.tonal(
    onPressed: _busy ? null : _export,
    child: Text(_busy ? 'Preparing…' : 'Download my data (JSON)'),
  );
}

class _Deletion extends ConsumerWidget {
  const new();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final privacy = ref.read(privacyRepositoryProvider);
    return switch (ref.watch(deletionProvider)) {
      AsyncData(:final value) when value.scheduledFor != null => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'Your account will be deleted on ${shortDate(value.scheduledFor!)}.'
            ' Until then you can change your mind.',
          ),
          const SizedBox(height: BarterlySpace.sm),
          OutlinedButton(
            onPressed: () async {
              await privacy.cancelDeletion();
              ref.invalidate(deletionProvider);
            },
            child: const Text('Keep my account'),
          ),
        ],
      ),
      AsyncData(:final value) => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'We erase your profile, photos, messages and everything that '
            'identifies you. Payments, invoices, signed agreements and '
            'disputes are kept, with your details removed. You have '
            '${value.graceDays} days to change your mind.',
          ),
          const SizedBox(height: BarterlySpace.sm),
          if (value.blockers.isNotEmpty) ...[
            const Text('Before you can delete your account:'),
            for (final blocker in value.blockers) Text('• $blocker'),
          ] else
            OutlinedButton(
              style: OutlinedButton.styleFrom(
                foregroundColor: BarterlyColors.danger,
              ),
              onPressed: () => _confirm(context, ref, value.graceDays),
              child: const Text('Delete my account'),
            ),
        ],
      ),
      AsyncError(:final error) => ErrorView(
        message: error is ApiError ? error.userMessage : '$error',
        onRetry: () => ref.invalidate(deletionProvider),
      ),
      _ => const LoadingView(),
    };
  }

  Future<void> _confirm(BuildContext context, WidgetRef ref, int days) async {
    final messenger = ScaffoldMessenger.of(context);
    final yes = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete your account?'),
        content: Text("After $days days this can't be undone."),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (!(yes ?? false)) return;
    try {
      await ref.read(privacyRepositoryProvider).requestDeletion();
    } on ApiError catch (error) {
      messenger.showSnackBar(SnackBar(content: Text(error.userMessage)));
    }
    ref.invalidate(deletionProvider);
  }
}

class _CorrectionDialog extends StatefulWidget {
  const new();

  @override
  State<_CorrectionDialog> createState() => _CorrectionDialogState();
}

class _CorrectionDialogState extends State<_CorrectionDialog> {
  final _field = TextEditingController();
  final _value = TextEditingController();

  @override
  void dispose() {
    _field.dispose();
    _value.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Ask for a correction'),
    content: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const Text(
          "Edit your profile yourself. Use this for what you can't change, "
          'like your phone number.',
        ),
        TextField(
          controller: _field,
          maxLength: 60,
          decoration: const InputDecoration(labelText: 'What is wrong'),
        ),
        TextField(
          controller: _value,
          maxLength: 500,
          decoration: const InputDecoration(labelText: 'What it should be'),
        ),
      ],
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Cancel'),
      ),
      FilledButton(
        onPressed: () {
          if (_field.text.trim().isEmpty || _value.text.trim().isEmpty) return;
          Navigator.pop(context, (
            field: _field.text.trim(),
            value: _value.text.trim(),
          ));
        },
        child: const Text('Send'),
      ),
    ],
  );
}
