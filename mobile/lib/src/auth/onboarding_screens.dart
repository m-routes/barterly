import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/auth/session.dart';
import 'package:barterly/src/auth/user.dart';
import 'package:barterly/src/providers.dart';
import 'package:barterly/src/theme/tokens.dart';
import 'package:barterly/src/widgets/brand.dart';
import 'package:barterly/src/widgets/states.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

/// Shown at launch while the session loads, or if loading it failed.
class SplashScreen extends ConsumerWidget {
  const new({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider);
    return Scaffold(
      body: SafeArea(
        child: switch (session) {
          SessionFailed(:final error) => ErrorView(
            title: "We couldn't load your account",
            message: error.userMessage,
            onRetry: () => ref.read(sessionProvider.notifier).reload(),
            secondary: OutlinedButton(
              onPressed: () => ref.read(sessionProvider.notifier).signOut(),
              child: const Text('Sign out'),
            ),
          ),
          _ => const LoadingView(label: 'Loading Barterly…'),
        },
      ),
    );
  }
}

/// First sign-in: the account has no role yet. This app is for talent.
class JoinAsTalentScreen extends ConsumerStatefulWidget {
  const new({super.key});

  @override
  ConsumerState<JoinAsTalentScreen> createState() => _JoinState();
}

class _JoinState extends ConsumerState<JoinAsTalentScreen> {
  bool _busy = false;
  String? _error;

  Future<void> _join() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(authRepositoryProvider).chooseTalentRole();
      await ref.read(sessionProvider.notifier).reload();
    } on ApiError catch (error) {
      if (error.code == 'role_already_set') {
        // Chosen on another device: carry on with what the API has.
        await ref.read(sessionProvider.notifier).reload();
      } else if (mounted) {
        setState(() => _error = error.userMessage);
      }
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
            Text('Join as talent', style: theme.textTheme.headlineMedium),
            const SizedBox(height: BarterlySpace.md),
            Text(
              'Artists, creators, chefs, guides and more: trade your skills '
              'for stays, meals or pay at places across India.',
              style: theme.textTheme.bodyLarge,
            ),
            const SizedBox(height: BarterlySpace.lg),
            Text(
              'Run a hostel, homestay, café or tour? Use the Barterly vendor '
              'console on the web instead. Your account can only be one of '
              'the two.',
              style: theme.textTheme.bodyMedium?.copyWith(
                color: BarterlyColors.inkMuted,
              ),
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
              onPressed: _busy ? null : _join,
              child: Text(_busy ? 'Joining…' : 'Join as talent'),
            ),
            const SizedBox(height: BarterlySpace.md),
            TextButton(
              onPressed: _busy
                  ? null
                  : () => ref.read(sessionProvider.notifier).signOut(),
              child: const Text('Sign out'),
            ),
          ],
        ),
      ),
    );
  }
}

/// Vendors and admins signed in to the talent app.
class WrongAppScreen extends ConsumerWidget {
  const new({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider);
    final role = session is SignedIn ? session.user.role : UserRole.none;
    final message = role == UserRole.admin
        ? 'Admins work in the Barterly admin console.'
        : 'Your account is a vendor account. Post gigs and review talent in '
              'the Barterly vendor console on the web.';
    return Scaffold(
      appBar: AppBar(title: const BrandMark()),
      body: SafeArea(
        child: EmptyState(
          icon: Icons.storefront_outlined,
          title: 'This app is for talent',
          message: message,
          action: OutlinedButton(
            onPressed: () => ref.read(sessionProvider.notifier).signOut(),
            child: const Text('Sign out'),
          ),
        ),
      ),
    );
  }
}
