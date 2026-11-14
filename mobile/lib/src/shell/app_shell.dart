import 'package:barterly/src/apply/outbox.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

/// The bottom bar around the four tabs. Each tab keeps its own navigation
/// stack ([StatefulShellRoute.indexedStack]).
///
/// It also keeps the application outbox running while the talent is in the
/// app, so queued applications are sent when the network returns, whichever
/// tab is open.
class AppShell extends ConsumerWidget {
  const new({required this.shell, super.key});

  final StatefulNavigationShell shell;

  static const destinations = [
    NavigationDestination(
      icon: Icon(Icons.travel_explore_outlined),
      selectedIcon: Icon(Icons.travel_explore),
      label: 'Discover',
    ),
    NavigationDestination(
      icon: Icon(Icons.luggage_outlined),
      selectedIcon: Icon(Icons.luggage),
      label: 'My trips',
    ),
    NavigationDestination(
      icon: Icon(Icons.account_balance_wallet_outlined),
      selectedIcon: Icon(Icons.account_balance_wallet),
      label: 'Wallet',
    ),
    NavigationDestination(
      icon: Icon(Icons.person_outline),
      selectedIcon: Icon(Icons.person),
      label: 'Profile',
    ),
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.listen(outboxProvider, (_, _) {});
    return Scaffold(
      body: shell,
      bottomNavigationBar: NavigationBar(
        selectedIndex: shell.currentIndex,
        destinations: destinations,
        onDestinationSelected: (index) => shell.goBranch(
          index,
          // Tapping the current tab again goes back to its first page.
          initialLocation: index == shell.currentIndex,
        ),
      ),
    );
  }
}
