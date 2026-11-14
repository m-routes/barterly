import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/foundation.dart';

/// Which backend the app talks to. Chosen at build time:
///
///     flutter run --dart-define-from-file=env/staging.json
///
/// Files in `env/` hold public config (URLs, Firebase app ids); Firebase API keys
/// come from the uncommitted env/firebase-keys.json (second --dart-define-from-file).
enum AppEnv {
  local,
  staging,
  production;

  static AppEnv parse(String value) => switch (value) {
    'staging' => staging,
    'production' => production,
    _ => local,
  };
}

@immutable
class AppConfig {
  const new({
    required this.env,
    required this.apiBaseUrl,
    this.firebase,
    this.sentryDsn = '',
    this.mapTileUrl = defaultMapTileUrl,
  });

  /// Reads the `--dart-define` values baked in at build time.
  factory fromEnvironment() {
    const env = String.fromEnvironment('BARTERLY_ENV', defaultValue: 'local');
    const baseUrl = String.fromEnvironment('API_BASE_URL');
    final appEnv = AppEnv.parse(env);
    return AppConfig(
      env: appEnv,
      apiBaseUrl: baseUrl.isNotEmpty ? baseUrl : _defaultBaseUrl(appEnv),
      firebase: _firebaseOptions(),
      // Looks redundant to the analyzer (no define at analysis time), but it is
      // set per build from env/*.json.
      // ignore: avoid_redundant_argument_values
      sentryDsn: const String.fromEnvironment('SENTRY_DSN'),
      // Set per build when a different tile server is used.
      // ignore: avoid_redundant_argument_values
      mapTileUrl: const String.fromEnvironment(
        'MAP_TILE_URL',
        defaultValue: defaultMapTileUrl,
      ),
    );
  }

  final AppEnv env;

  /// OpenStreetMap's standard tiles. Their tile policy allows light use with
  /// visible attribution and an identifying User-Agent; point MAP_TILE_URL at
  /// a commercial or self-hosted tile server before traffic grows.
  static const defaultMapTileUrl =
      'https://tile.openstreetmap.org/{z}/{x}/{y}.png';

  /// Origin of the Django API, without a trailing slash (paths start /api/v1/).
  final String apiBaseUrl;

  /// Null when this build has no Firebase app: sign-in is unavailable.
  final FirebaseOptions? firebase;
  final String sentryDsn;

  /// Map tile URL template with {z}/{x}/{y} (`--dart-define=MAP_TILE_URL=…`).
  final String mapTileUrl;

  bool get crashReportingEnabled => sentryDsn.isNotEmpty;

  static String _defaultBaseUrl(AppEnv env) => switch (env) {
    AppEnv.production =>
      'https://barterly-api-production-430344535597.asia-south1.run.app',
    AppEnv.staging =>
      'https://barterly-api-staging-430344535597.asia-south1.run.app',
    // The Android emulator reaches the host machine at 10.0.2.2.
    AppEnv.local =>
      defaultTargetPlatform == TargetPlatform.android
          ? 'http://10.0.2.2:8000'
          : 'http://localhost:8000',
  };

  static FirebaseOptions? _firebaseOptions() {
    const projectId = String.fromEnvironment('FIREBASE_PROJECT_ID');
    const senderId = String.fromEnvironment('FIREBASE_MESSAGING_SENDER_ID');
    // Firebase issues a separate API key and app id per platform.
    final ios = defaultTargetPlatform == TargetPlatform.iOS;
    final apiKey = ios
        ? const String.fromEnvironment('FIREBASE_IOS_API_KEY')
        : const String.fromEnvironment('FIREBASE_ANDROID_API_KEY');
    final appId = ios
        ? const String.fromEnvironment('FIREBASE_IOS_APP_ID')
        : const String.fromEnvironment('FIREBASE_ANDROID_APP_ID');
    if (apiKey.isEmpty || projectId.isEmpty || appId.isEmpty) return null;
    return FirebaseOptions(
      apiKey: apiKey,
      appId: appId,
      messagingSenderId: senderId,
      projectId: projectId,
      iosBundleId: 'in.barterly.barterly',
    );
  }
}

/// Whether to turn on Firebase's `appVerificationDisabledForTesting`: only for
/// local debug builds, which sign in with Firebase test numbers.
bool skipAppVerification(AppEnv env, {required bool debug}) =>
    debug && env == AppEnv.local;
