import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/auth/session.dart';
import 'package:barterly/src/privacy/agreements_checklist.dart';
import 'package:barterly/src/providers.dart';
import 'package:barterly/src/router.dart';
import 'package:barterly/src/theme/tokens.dart';
import 'package:barterly/src/widgets/brand.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

/// The terms or the privacy policy changed: accept the new versions (two
/// separate consents) before going on, or delete the account instead.
class ConsentScreen extends ConsumerStatefulWidget {
  const new({super.key});

  @override
  ConsumerState<ConsentScreen> createState() => _ConsentState();
}

class _ConsentState extends ConsumerState<ConsentScreen> {
  bool _terms = false;
  bool _privacy = false;
  bool _busy = false;
  String? _error;

  Future<void> _accept() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final privacy = ref.read(privacyRepositoryProvider);
      await privacy.setConsent('terms', granted: true);
      await privacy.setConsent('privacy', granted: true);
      await ref.read(sessionProvider.notifier).reload();
    } on ApiError catch (error) {
      if (mounted) setState(() => _error = error.userMessage);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const BrandMark()),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(BarterlySpace.xl),
          children: [
            Text(
              'Our terms have changed',
              style: theme.textTheme.headlineMedium,
            ),
            const SizedBox(height: BarterlySpace.md),
            Text(
              'Please read and accept the current versions to keep using '
              'Barterly.',
              style: theme.textTheme.bodyLarge,
            ),
            const SizedBox(height: BarterlySpace.lg),
            AgreementsChecklist(
              terms: _terms,
              privacy: _privacy,
              onTerms: (v) => setState(() => _terms = v),
              onPrivacy: (v) => setState(() => _privacy = v),
            ),
            if (_error != null) ...[
              const SizedBox(height: BarterlySpace.lg),
              Text(
                _error!,
                style: const TextStyle(color: BarterlyColors.danger),
              ),
            ],
            const SizedBox(height: BarterlySpace.xl),
            FilledButton(
              onPressed: _busy || !_terms || !_privacy ? null : _accept,
              child: Text(_busy ? 'Saving…' : 'Accept and continue'),
            ),
            const SizedBox(height: BarterlySpace.md),
            TextButton(
              onPressed: _busy ? null : () => context.push(Routes.privacy),
              child: const Text("Don't agree? Delete your account"),
            ),
          ],
        ),
      ),
    );
  }
}
