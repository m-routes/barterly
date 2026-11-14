import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:barterly/src/api/token_store.dart';
import 'package:barterly/src/app.dart';
import 'package:barterly/src/auth/phone_auth.dart';
import 'package:barterly/src/config/env.dart';
import 'package:barterly/src/platform/key_value_store.dart';
import 'package:barterly/src/platform/media_picker.dart';
import 'package:barterly/src/platform/network_status.dart';
import 'package:barterly/src/platform/url_opener.dart';
import 'package:barterly/src/providers.dart';
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart' show Size;

/// A recorded request and a canned answer.
typedef Handler = FutureOr<FakeResponse> Function(RequestOptions request);

class FakeResponse {
  const new(this.status, [this.body, this.headers = const {}]);

  final int status;
  final Object? body;
  final Map<String, String> headers;
}

FakeResponse ok(Object? body) => FakeResponse(200, body);

FakeResponse apiError(
  int status,
  String code, [
  String? message,
  Map<String, Object?> details = const {},
]) => FakeResponse(status, {
  'code': code,
  'message': message ?? code,
  'details': details,
});

/// What a signed-in talent's tabs ask for when a test doesn't care: no gigs,
/// no applications, no saved searches.
final Map<String, Handler> talentDefaults = {
  'GET /api/v1/gigs/': (_) => ok(emptyPage),
  'GET /api/v1/applications/mine/': (_) => ok(<Object?>[]),
  'GET /api/v1/gigs/saved-searches/': (_) => ok(<Object?>[]),
};

const Map<String, List<Object?>?> emptyPage = {
  'results': <Object?>[],
  'next_cursor': null,
  'next': null,
};

/// Answers Dio requests from [routes] ("METHOD /path/") without a network.
/// [talentDefaults] answer anything not listed; other requests fail the test.
/// Set [offline] to fail every request like a dropped connection.
class FakeApi implements HttpClientAdapter {
  new([Map<String, Handler>? routes])
    : routes = {...talentDefaults, ...?routes};

  bool offline = false;

  final Map<String, Handler> routes;
  final List<RequestOptions> requests = [];

  List<String> get calls => [for (final r in requests) '${r.method} ${r.path}'];

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options);
    if (offline) {
      throw DioException.connectionError(
        requestOptions: options,
        reason: 'offline (test)',
      );
    }
    final handler = routes['${options.method} ${options.path}'];
    if (handler == null) {
      fail('Unexpected request: ${options.method} ${options.path}');
    }
    final response = await handler(options);
    return ResponseBody.fromString(
      response.body == null ? '' : jsonEncode(response.body),
      response.status,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
        for (final MapEntry(:key, :value) in response.headers.entries)
          key: [value],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

const Map<String, Object?> talentJson = {
  'id': '8b0c1d2e-0000-4000-8000-000000000002',
  'phone': '+919876543210',
  'email': null,
  'role': 'talent',
  'is_active': true,
  'profile_complete': true,
  'created_at': '2026-11-01T10:00:00Z',
};

Map<String, Object?> userJson({String role = 'talent', bool complete = true}) =>
    {...talentJson, 'role': role, 'profile_complete': complete};

const skillsJson = [
  {'slug': 'mural-painting', 'name': 'Mural painting'},
  {'slug': 'photography', 'name': 'Photography'},
  {'slug': 'barista', 'name': 'Barista'},
];

/// Phone sign-in that never touches Firebase.
class FakePhoneAuth implements PhoneAuth {
  new({this.sendError, this.validCode = '123456'});

  final PhoneAuthException? sendError;
  final String validCode;
  final List<String> sentTo = [];
  bool signedOut = false;

  @override
  Future<PhoneVerification> sendCode(String phoneE164) async {
    sentTo.add(phoneE164);
    if (sendError != null) throw sendError!;
    return CodeSent((code) async {
      if (code != validCode) {
        throw PhoneAuthException.fromCode('invalid-verification-code');
      }
      return 'firebase-id-token';
    });
  }

  @override
  Future<void> signOut() async => signedOut = true;
}

const testConfig = AppConfig(env: AppEnv.local, apiBaseUrl: 'http://api.test');

/// Camera and gallery picks from a queue the test fills.
class FakeMediaPicker implements MediaPicker {
  final List<PickedFile?> photos = [];
  final List<PickedFile?> videos = [];
  final Map<String, List<int>> files = {};
  final List<String> discarded = [];
  final List<PickSource> sources = [];

  /// Queues a photo of [size] bytes and returns it.
  PickedFile addPhoto(String name, {int size = 1024}) {
    final file = PickedFile(
      path: '/kept/$name',
      name: name,
      contentType: contentTypeFor(name) ?? 'image/jpeg',
      sizeBytes: size,
    );
    files[file.path] = List.filled(size.clamp(0, 4096), 1);
    photos.add(file);
    return file;
  }

  @override
  Future<PickedFile?> pickPhoto(PickSource source) async {
    sources.add(source);
    return photos.isEmpty ? null : photos.removeAt(0);
  }

  @override
  Future<PickedFile?> pickVideo(PickSource source) async {
    sources.add(source);
    return videos.isEmpty ? null : videos.removeAt(0);
  }

  @override
  Future<List<int>> read(String path) async =>
      files[path] ?? (throw StateError('no file $path'));

  @override
  Future<void> discard(String path) async => discarded.add(path);
}

class FakeUrlOpener implements UrlOpener {
  final List<Uri> inApp = [];
  final List<Uri> external = [];

  @override
  Future<bool> openInApp(Uri url) async {
    inApp.add(url);
    return true;
  }

  @override
  Future<bool> openExternal(Uri url) async {
    external.add(url);
    return true;
  }
}

/// Overrides that put the app on a fake API, in-memory tokens and storage,
/// fake sign-in, and a network switch the test controls.
List<Override> testOverrides({
  required FakeApi api,
  TokenStore? tokens,
  PhoneAuth? phoneAuth,
  KeyValueStore? store,
  NetworkStatus? network,
  MediaPicker? picker,
  UrlOpener? urls,
}) => [
  appConfigProvider.overrideWithValue(testConfig),
  httpAdapterProvider.overrideWithValue(api),
  tokenStoreProvider.overrideWithValue(tokens ?? MemoryTokenStore()),
  phoneAuthProvider.overrideWithValue(phoneAuth ?? FakePhoneAuth()),
  keyValueStoreProvider.overrideWithValue(store ?? MemoryKeyValueStore()),
  networkStatusProvider.overrideWithValue(network ?? FakeNetworkStatus()),
  mediaPickerProvider.overrideWithValue(picker ?? FakeMediaPicker()),
  urlOpenerProvider.overrideWithValue(urls ?? FakeUrlOpener()),
];

/// Pumps the whole app on fakes and lets the session load.
Future<void> pumpApp(
  WidgetTester tester, {
  required FakeApi api,
  TokenStore? tokens,
  PhoneAuth? phoneAuth,
  KeyValueStore? store,
  NetworkStatus? network,
  MediaPicker? picker,
  UrlOpener? urls,
  List<Override> extra = const [],
}) async {
  await tester.pumpWidget(
    ProviderScope(
      // Fail fast in tests instead of Riverpod's automatic retries.
      retry: (_, _) => null,
      overrides: testOverrides(
        api: api,
        tokens: tokens,
        phoneAuth: phoneAuth,
        store: store,
        network: network,
        picker: picker,
        urls: urls,
      )..addAll(extra),
      child: const BarterlyApp(brandFonts: false),
    ),
  );
  await tester.pumpAndSettle();
}

const signedInTokens = Tokens(access: 'access-1', refresh: 'refresh-1');

/// A signed-in talent with a complete profile, plus [routes].
FakeApi talentApi([Map<String, Handler>? routes]) => FakeApi({
  'GET /api/v1/me/': (_) => ok(talentJson),
  'GET /api/v1/profiles/talent/me/': (_) => ok({
    'display_name': 'Asha Rao',
    'bio': 'Muralist from Goa.',
    'talent_type': 'artist',
    'skills': ['mural-painting'],
    'languages': ['en'],
    'home_city': 'Panaji',
    'instagram_handle': 'asha.paints',
    'profile_complete': true,
    'missing_fields': <String>[],
  }),
  ...?routes,
});

/// A phone-sized screen (390 x 844), reset after the test.
void usePhoneScreen(WidgetTester tester) {
  tester.view.physicalSize = const Size(1170, 2532);
  tester.view.devicePixelRatio = 3;
  addTearDown(tester.view.reset);
}
