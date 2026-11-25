import 'package:barterly/src/analytics/analytics.dart';
import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/auth/session.dart';
import 'package:barterly/src/auth/user.dart';
import 'package:barterly/src/privacy/agreements_checklist.dart';
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

final FutureProvider<List<String>> _inviteRolesProvider =
    FutureProvider.autoDispose<List<String>>(
      (ref) => ref.watch(authRepositoryProvider).inviteRoles(),
    );

class _JoinState extends ConsumerState<JoinAsTalentScreen> {
  final _invite = TextEditingController();
  bool _askInvite = false;
  String? _inviteError;
  bool _adult = false;
  bool _terms = false;
  bool _privacy = false;
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _invite.dispose();
    super.dispose();
  }

  bool get _needsInvite =>
      _askInvite ||
      (ref.read(_inviteRolesProvider).value?.contains('talent') ?? false);

  Future<void> _join() async {
    final code = _invite.text.trim();
    if (_needsInvite && code.isEmpty) {
      setState(() {
        _askInvite = true;
        _inviteError = 'Enter the invite code we sent you.';
      });
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
      _inviteError = null;
    });
    final analytics = ref.read(analyticsProvider);
    try {
      await ref
          .read(authRepositoryProvider)
          .chooseTalentRole(inviteCode: _needsInvite ? code : null);
      if (_needsInvite) analytics.track('invite_entered', {'ok': true});
      await ref.read(sessionProvider.notifier).reload();
    } on ApiError catch (error) {
      if (error.code == 'invite_required' || error.code == 'invite_invalid') {
        if (error.code == 'invite_invalid') {
          analytics.track('invite_entered', {'ok': false});
        }
        if (mounted) {
          setState(() {
            _askInvite = true;
            _inviteError = error.message;
          });
        }
      } else if (error.code == 'role_already_set') {
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
            const SizedBox(height: BarterlySpace.lg),
            if (_askInvite ||
                (ref.watch(_inviteRolesProvider).value?.contains('talent') ??
                    false)) ...[
              TextField(
                controller: _invite,
                autocorrect: false,
                textCapitalization: TextCapitalization.characters,
                maxLength: 20,
                decoration: InputDecoration(
                  labelText: 'Invite code',
                  helperText:
                      'Barterly is invite-only for now. '
                      'It looks like ABCD-2345.',
                  errorText: _inviteError,
                ),
              ),
              const SizedBox(height: BarterlySpace.md),
            ],
            AgreementsChecklist(
              adult: _adult,
              terms: _terms,
              privacy: _privacy,
              onAdult: (v) => setState(() => _adult = v),
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
              onPressed: _busy || !(_adult && _terms && _privacy)
                  ? null
                  : _join,
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
