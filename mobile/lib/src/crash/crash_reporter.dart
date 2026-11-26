import 'package:barterly/src/config/env.dart';
import 'package:flutter/foundation.dart';
import 'package:sentry_flutter/sentry_flutter.dart';

/// Where uncaught errors go. Sentry when a DSN is configured, else nowhere
/// (debug builds still print them).
abstract interface class CrashReporter {
  Future<void> report(Object error, StackTrace? stack, {String? context});

  /// Ties reports to an account id (never the phone number).
  Future<void> setUser(String? userId);
}

class NoopCrashReporter implements CrashReporter {
  const new();

  @override
  Future<void> report(
    Object error,
    StackTrace? stack, {
    String? context,
  }) async {
    debugPrint(
      'Unreported error${context == null ? '' : ' ($context)'}: $error',
    );
  }

  @override
  Future<void> setUser(String? userId) async {}
}

class SentryCrashReporter implements CrashReporter {
  const new();

  /// Starts Sentry, then runs [appRunner] inside its error zone.
  static Future<void> init(
    AppConfig config,
    Future<void> Function() appRunner,
  ) => SentryFlutter.init((options) {
    // Release builds name themselves like the debug symbols that
    // tool/build_release.sh uploads (barterly@<version>+<build>), so
    // obfuscated stack traces map back.
    const release = String.fromEnvironment('SENTRY_RELEASE');
    const dist = String.fromEnvironment('SENTRY_DIST');
    options
      ..dsn = config.sentryDsn
      ..environment = config.env.name
      // Phone numbers are identifiers here; keep them out of reports.
      ..sendDefaultPii = false
      ..tracesSampleRate = 0;
    if (release.isNotEmpty) options.release = release;
    if (dist.isNotEmpty) options.dist = dist;
  }, appRunner: appRunner);

  @override
  Future<void> report(
    Object error,
    StackTrace? stack, {
    String? context,
  }) async {
    await Sentry.captureException(
      error,
      stackTrace: stack,
      withScope: context == null
          ? null
          : (scope) => scope.setTag('context', context),
    );
  }

  @override
  Future<void> setUser(String? userId) async {
    await Sentry.configureScope(
      (scope) => scope.setUser(userId == null ? null : SentryUser(id: userId)),
    );
  }
}
