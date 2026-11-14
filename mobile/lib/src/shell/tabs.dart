import 'package:barterly/src/auth/session.dart';
import 'package:barterly/src/profile/talent_profile.dart';
import 'package:barterly/src/providers.dart';
import 'package:barterly/src/theme/tokens.dart';
import 'package:barterly/src/widgets/states.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

/// The Wallet and Profile tabs. Discover and My trips live in discover/ and
/// apply/.

class WalletTab extends StatelessWidget {
  const new({super.key});

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Wallet')),
    body: const EmptyState(
      icon: Icons.account_balance_wallet_outlined,
      title: 'Nothing here yet',
      message: 'Stipends and payments for paid gigs will be tracked here.',
    ),
  );
}

final FutureProvider<TalentProfile?> myProfileProvider =
    FutureProvider.autoDispose<TalentProfile?>(
      (ref) => ref.watch(profileRepositoryProvider).fetchTalentProfile(),
    );

class ProfileTab extends ConsumerWidget {
  const new({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final profile = ref.watch(myProfileProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Profile')),
      body: switch (profile) {
        AsyncData(:final value) => _ProfileSummary(profile: value),
        AsyncError() => ErrorView(
          title: "We couldn't load your profile",
          message: 'Check your connection and try again.',
          onRetry: () => ref.invalidate(myProfileProvider),
        ),
        _ => const LoadingView(label: 'Loading your profile…'),
      },
    );
  }
}

class _ProfileSummary extends ConsumerWidget {
  const new({required this.profile});

  final TalentProfile? profile;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final session = ref.watch(sessionProvider);
    final phone = session is SignedIn ? session.user.phone : '';
    final p = profile;
    return ListView(
      padding: const EdgeInsets.all(BarterlySpace.xl),
      children: [
        Text(
          p?.displayName ?? 'Your profile',
          style: theme.textTheme.headlineSmall,
        ),
        if (p?.talentType != null) ...[
          const SizedBox(height: BarterlySpace.xs),
          Text(
            p!.talentType!.label,
            style: theme.textTheme.bodyLarge?.copyWith(
              color: BarterlyColors.accent,
            ),
          ),
        ],
        if (p != null && p.homeCity.isNotEmpty) ...[
          const SizedBox(height: BarterlySpace.xs),
          Text(
            p.homeCity,
            style: const TextStyle(color: BarterlyColors.inkMuted),
          ),
        ],
        if (p != null && p.bio.isNotEmpty) ...[
          const SizedBox(height: BarterlySpace.lg),
          Text(p.bio, style: theme.textTheme.bodyLarge),
        ],
        const SizedBox(height: BarterlySpace.xl),
        OutlinedButton.icon(
          onPressed: () async {
            await context.push('/profile/edit');
            ref.invalidate(myProfileProvider);
          },
          icon: const Icon(Icons.edit_outlined),
          label: const Text('Edit profile'),
        ),
        const SizedBox(height: BarterlySpace.md),
        ListTile(
          contentPadding: EdgeInsets.zero,
          leading: const Icon(Icons.verified_user_outlined),
          title: const Text('Verification and badges'),
          subtitle: const Text('ID, selfie and Instagram'),
          trailing: const Icon(Icons.chevron_right),
          onTap: () => context.push('/profile/verification'),
        ),
        const SizedBox(height: BarterlySpace.md),
        const Divider(),
        ListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Signed in as'),
          subtitle: Text(phone),
        ),
        TextButton(
          onPressed: () => ref.read(sessionProvider.notifier).signOut(),
          child: const Text('Sign out'),
        ),
      ],
    );
  }
}
