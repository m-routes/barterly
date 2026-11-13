import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

/// The bottom bar around the four tabs. Each tab keeps its own navigation
/// stack ([StatefulShellRoute.indexedStack]).
class AppShell extends StatelessWidget {
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
  Widget build(BuildContext context) {
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
