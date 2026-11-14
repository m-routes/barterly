import 'package:barterly/src/apply/apply_screen.dart';
import 'package:barterly/src/apply/my_applications_screen.dart';
import 'package:barterly/src/auth/login_screen.dart';
import 'package:barterly/src/auth/onboarding_screens.dart';
import 'package:barterly/src/auth/session.dart';
import 'package:barterly/src/auth/user.dart';
import 'package:barterly/src/discover/discover_screen.dart';
import 'package:barterly/src/discover/gig_detail_screen.dart';
import 'package:barterly/src/profile/profile_setup_screen.dart';
import 'package:barterly/src/shell/app_shell.dart';
import 'package:barterly/src/shell/tabs.dart';
import 'package:barterly/src/verification/verification_screen.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

abstract final class Routes {
  static const splash = '/splash';
  static const login = '/login';
  static const join = '/join';
  static const wrongApp = '/wrong-app';
  static const setup = '/setup';
  static const discover = '/discover';
  static const trips = '/trips';
  static const wallet = '/wallet';
  static const profile = '/profile';
  static const editProfile = '/profile/edit';
  static const verification = '/profile/verification';
  static String gig(String id) => '/discover/gig/$id';
  static String apply(String id) => '/discover/gig/$id/apply';

  /// Screens that only make sense before the person is fully in.
  static const Set<String> gates = {splash, login, join, wrongApp, setup};
}

/// Where the person should be, given the session, or null to stay put.
///
/// Pure, so the rules are tested without widgets (test/router_test.dart).
String? redirectFor(SessionState session, String location) {
  String? goTo(String target) => location == target ? null : target;

  return switch (session) {
    SessionLoading() || SessionFailed() => goTo(Routes.splash),
    SignedOut() => goTo(Routes.login),
    SignedIn(:final user) => switch (user.role) {
      UserRole.none => goTo(Routes.join),
      UserRole.vendor || UserRole.admin => goTo(Routes.wrongApp),
      UserRole.talent when !user.profileComplete => goTo(Routes.setup),
      UserRole.talent =>
        Routes.gates.contains(location) ? Routes.discover : null,
    },
  };
}

final routerProvider = Provider<GoRouter>((ref) {
  // go_router re-runs redirect when this ticks; the session drives it.
  final refresh = ValueNotifier<SessionState>(ref.read(sessionProvider));
  ref
    ..listen(sessionProvider, (_, next) => refresh.value = next)
    ..onDispose(refresh.dispose);

  final router = GoRouter(
    initialLocation: Routes.splash,
    refreshListenable: refresh,
    redirect: (context, state) =>
        redirectFor(ref.read(sessionProvider), state.matchedLocation),
    routes: [
      GoRoute(path: Routes.splash, builder: (_, _) => const SplashScreen()),
      GoRoute(path: Routes.login, builder: (_, _) => const LoginScreen()),
      GoRoute(path: Routes.join, builder: (_, _) => const JoinAsTalentScreen()),
      GoRoute(path: Routes.wrongApp, builder: (_, _) => const WrongAppScreen()),
      GoRoute(
        path: Routes.setup,
        builder: (_, _) => const ProfileSetupScreen(),
      ),
      StatefulShellRoute.indexedStack(
        builder: (_, _, shell) => AppShell(shell: shell),
        branches: [
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: Routes.discover,
                builder: (_, _) => const DiscoverScreen(),
                routes: [
                  GoRoute(
                    path: 'gig/:id',
                    builder: (_, state) =>
                        GigDetailScreen(gigId: state.pathParameters['id']!),
                    routes: [
                      GoRoute(
                        path: 'apply',
                        builder: (_, state) =>
                            ApplyScreen(gigId: state.pathParameters['id']!),
                      ),
                    ],
                  ),
                ],
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: Routes.trips,
                builder: (_, _) => const MyApplicationsScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: Routes.wallet,
                builder: (_, _) => const WalletTab(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: Routes.profile,
                builder: (_, _) => const ProfileTab(),
                routes: [
                  GoRoute(
                    path: 'edit',
                    builder: (_, _) => const ProfileSetupScreen(editing: true),
                  ),
                  GoRoute(
                    path: 'verification',
                    builder: (_, _) => const VerificationScreen(),
                  ),
                ],
              ),
            ],
          ),
        ],
      ),
    ],
  );
  ref.onDispose(router.dispose);
  return router;
});
