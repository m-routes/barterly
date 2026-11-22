import 'package:barterly/src/agreements/agreements_repository.dart';
import 'package:barterly/src/api/api_client.dart';
import 'package:barterly/src/api/token_store.dart';
import 'package:barterly/src/apply/applications_repository.dart';
import 'package:barterly/src/attendance/attendance_repository.dart';
import 'package:barterly/src/attendance/location.dart';
import 'package:barterly/src/auth/auth_repository.dart';
import 'package:barterly/src/auth/phone_auth.dart';
import 'package:barterly/src/auth/session.dart';
import 'package:barterly/src/chat/chat_repository.dart';
import 'package:barterly/src/chat/chat_transport.dart';
import 'package:barterly/src/config/env.dart';
import 'package:barterly/src/crash/crash_reporter.dart';
import 'package:barterly/src/deliverables/deliverables_repository.dart';
import 'package:barterly/src/discover/gigs_repository.dart';
import 'package:barterly/src/notifications/notifications_repository.dart';
import 'package:barterly/src/notifications/push.dart';
import 'package:barterly/src/notifications/push_registrar.dart';
import 'package:barterly/src/platform/calendar.dart';
import 'package:barterly/src/platform/key_value_store.dart';
import 'package:barterly/src/platform/media_picker.dart';
import 'package:barterly/src/platform/network_status.dart';
import 'package:barterly/src/platform/url_opener.dart';
import 'package:barterly/src/privacy/privacy_repository.dart';
import 'package:barterly/src/profile/profile_repository.dart';
import 'package:barterly/src/reviews/reviews_repository.dart';
import 'package:barterly/src/trips/trip_models.dart';
import 'package:barterly/src/verification/verification_repository.dart';
import 'package:dio/dio.dart';
import 'package:flutter_map/flutter_map.dart' show TileProvider;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show FutureProviderFamily;
import 'package:material_ui/material_ui.dart'
    show GlobalKey, ScaffoldMessengerState;

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

final gigsRepositoryProvider = Provider<GigsRepository>(
  (ref) => GigsRepository(ref.watch(dioProvider)),
);

final applicationsRepositoryProvider = Provider<ApplicationsRepository>(
  (ref) => ApplicationsRepository(ref.watch(dioProvider)),
);

final agreementsRepositoryProvider = Provider<AgreementsRepository>(
  (ref) => AgreementsRepository(ref.watch(dioProvider)),
);

final chatRepositoryProvider = Provider<ChatRepository>(
  (ref) => ChatRepository(ref.watch(dioProvider)),
);

/// How chat screens get messages. Polling today; swap for a WebSocket
/// transport without touching the screens.
final chatTransportProvider = Provider<ChatTransport>(
  (ref) => PollingChatTransport(ref.watch(chatRepositoryProvider)),
);

final verificationRepositoryProvider = Provider<VerificationRepository>(
  (ref) => VerificationRepository(ref.watch(dioProvider)),
);

/// For PUTs to signed Cloud Storage URLs: no base URL and no auth header.
final storageDioProvider = Provider<Dio>((ref) {
  final dio = Dio(
    BaseOptions(
      connectTimeout: const Duration(seconds: 15),
      sendTimeout: const Duration(minutes: 5),
      receiveTimeout: const Duration(seconds: 30),
    ),
  );
  final adapter = ref.watch(httpAdapterProvider);
  if (adapter != null) dio.httpClientAdapter = adapter;
  return dio;
});

final mediaUploaderProvider = Provider<MediaUploader>(
  (ref) => MediaUploader(
    api: ref.watch(dioProvider),
    storage: ref.watch(storageDioProvider),
  ),
);

/// Check-in passes (kept on the device for offline use) and hour logs.
final attendanceRepositoryProvider = Provider<AttendanceRepository>(
  (ref) => AttendanceRepository(
    ref.watch(dioProvider),
    ref.watch(keyValueStoreProvider),
  ),
);

final privacyRepositoryProvider = Provider<PrivacyRepository>(
  (ref) => PrivacyRepository(ref.watch(dioProvider)),
);

final reviewsRepositoryProvider = Provider<ReviewsRepository>(
  (ref) => ReviewsRepository(ref.watch(dioProvider)),
);

final deliverablesRepositoryProvider = Provider<DeliverablesRepository>(
  (ref) => DeliverablesRepository(ref.watch(dioProvider)),
);

/// Where the talent is when they open their pass (optional; never blocks).
final locationReaderProvider = Provider<LocationReader>(
  (ref) => GeolocatorReader(),
);

/// The time, so screens with clocks can be tested.
final clockProvider = Provider<DateTime Function()>((ref) => DateTime.now);

/// On-device JSON storage (offline feed, queued applications).
final keyValueStoreProvider = Provider<KeyValueStore>(
  (ref) => SharedPrefsStore(),
);

final networkStatusProvider = Provider<NetworkStatus>(
  (ref) => ConnectivityNetworkStatus(),
);

/// True while some network is up. Starts with the current state.
final onlineProvider = StreamProvider<bool>((ref) async* {
  final network = ref.watch(networkStatusProvider);
  yield await network.isOnline();
  yield* network.changes;
});

final mediaPickerProvider = Provider<MediaPicker>(
  (ref) => ImagePickerMediaPicker(),
);

final urlOpenerProvider = Provider<UrlOpener>(
  (ref) => const LauncherUrlOpener(),
);

/// Null uses flutter_map's network tiles; tests swap in tiles from memory.
final mapTileProviderProvider = Provider<TileProvider?>((ref) => null);

/// The signed-in account's id, for keying what is stored on the device.
final currentUserIdProvider = Provider<String>((ref) {
  final session = ref.watch(sessionProvider);
  return session is SignedIn ? session.user.id : 'signed-out';
});

final notificationsRepositoryProvider = Provider<NotificationsRepository>(
  (ref) => NotificationsRepository(ref.watch(dioProvider)),
);

/// Firebase Cloud Messaging when Firebase started (main.dart), else nothing.
final pushMessagingProvider = Provider<PushMessaging>(
  (ref) => const NoPushMessaging(),
);

final pushRegistrarProvider = Provider<PushRegistrar>(PushRegistrar.new);

final FutureProvider<int> unreadCountProvider = FutureProvider.autoDispose<int>(
  (ref) => ref.watch(notificationsRepositoryProvider).unreadCount(),
);

/// The phone's calendar (tests swap in a fake).
final calendarProvider = Provider<CalendarService>(
  (ref) => const DeviceCalendar(),
);

final FutureProviderFamily<ApplicationDetail, String>
applicationDetailProvider = FutureProvider.autoDispose
    .family<ApplicationDetail, String>(
      (ref, id) => ref.watch(applicationsRepositoryProvider).detail(id),
    );

/// The app's ScaffoldMessenger, for banners shown from outside a screen (a push
/// that arrives while the app is open).
final scaffoldMessengerKeyProvider =
    Provider<GlobalKey<ScaffoldMessengerState>>(
      (ref) => GlobalKey<ScaffoldMessengerState>(),
    );
