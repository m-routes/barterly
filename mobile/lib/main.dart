import 'dart:async';

import 'package:barterly/src/app.dart';
import 'package:barterly/src/auth/phone_auth.dart';
import 'package:barterly/src/config/env.dart';
import 'package:barterly/src/crash/crash_reporter.dart';
import 'package:barterly/src/providers.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

/// Build with an environment file, e.g.
///
///     flutter run --dart-define-from-file=env/staging.json
Future<void> main() async {
  final config = AppConfig.fromEnvironment();

  Future<void> start() async {
    WidgetsFlutterBinding.ensureInitialized();
    final crash = config.crashReportingEnabled
        ? const SentryCrashReporter()
        : const NoopCrashReporter();

    var phoneAuth = const UnavailablePhoneAuth() as PhoneAuth;
    final firebase = config.firebase;
    if (firebase != null) {
      try {
        await Firebase.initializeApp(options: firebase);
        phoneAuth = FirebasePhoneAuth();
      } on Object catch (error, stack) {
        // Sign-in shows "not available" rather than the app failing to start.
        await crash.report(error, stack, context: 'firebase_init');
      }
    }

    runApp(
      ProviderScope(
        overrides: [
          appConfigProvider.overrideWithValue(config),
          phoneAuthProvider.overrideWithValue(phoneAuth),
          crashReporterProvider.overrideWithValue(crash),
        ],
        child: const BarterlyApp(),
      ),
    );
  }

  if (config.crashReportingEnabled) {
    // Sentry hooks Flutter and platform errors before the app starts.
    await SentryCrashReporter.init(config, start);
  } else {
    await start();
  }
}
