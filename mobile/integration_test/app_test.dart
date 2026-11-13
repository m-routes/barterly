import 'package:barterly/src/api/token_store.dart';
import 'package:barterly/src/app.dart';
import 'package:barterly/src/config/env.dart';
import 'package:barterly/src/providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

/// Runs on a device or simulator: `flutter test integration_test`.
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('a fresh install opens on sign-in', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          appConfigProvider.overrideWithValue(
            const AppConfig(env: AppEnv.local, apiBaseUrl: 'http://localhost'),
          ),
          // No stored tokens, so no network call is made.
          tokenStoreProvider.overrideWithValue(MemoryTokenStore()),
        ],
        child: const BarterlyApp(brandFonts: false),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Sign in to Barterly'), findsOneWidget);
  });
}
