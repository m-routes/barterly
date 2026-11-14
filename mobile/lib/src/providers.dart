import 'package:barterly/src/api/api_client.dart';
import 'package:barterly/src/api/token_store.dart';
import 'package:barterly/src/auth/auth_repository.dart';
import 'package:barterly/src/auth/phone_auth.dart';
import 'package:barterly/src/auth/session.dart';
import 'package:barterly/src/config/env.dart';
import 'package:barterly/src/crash/crash_reporter.dart';
import 'package:barterly/src/profile/profile_repository.dart';
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// App-wide dependencies. main.dart overrides the config and platform services;
/// tests override the repositories or the HTTP adapter.

final appConfigProvider = Provider<AppConfig>(
  (ref) => AppConfig.fromEnvironment(),
);

final tokenStoreProvider = Provider<TokenStore>((ref) => SecureTokenStore());

final phoneAuthProvider = Provider<PhoneAuth>(
  (ref) => const UnavailablePhoneAuth(),
);

final crashReporterProvider = Provider<CrashReporter>(
  (ref) => const NoopCrashReporter(),
);

/// Swap in a fake adapter to answer HTTP calls in tests.
final httpAdapterProvider = Provider<HttpClientAdapter?>((ref) => null);

final dioProvider = Provider<Dio>(
  (ref) => createApiClient(
    baseUrl: ref.watch(appConfigProvider).apiBaseUrl,
    tokens: ref.watch(tokenStoreProvider),
    adapter: ref.watch(httpAdapterProvider),
    onSessionExpired: () => ref.read(sessionProvider.notifier).expired(),
  ),
);

final authRepositoryProvider = Provider<AuthRepository>(
  (ref) => AuthRepository(
    dio: ref.watch(dioProvider),
    tokens: ref.watch(tokenStoreProvider),
  ),
);

final profileRepositoryProvider = Provider<ProfileRepository>(
  (ref) => ProfileRepository(ref.watch(dioProvider)),
);
