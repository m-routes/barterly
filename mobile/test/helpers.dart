import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:barterly/src/api/token_store.dart';
import 'package:barterly/src/app.dart';
import 'package:barterly/src/auth/phone_auth.dart';
import 'package:barterly/src/config/env.dart';
import 'package:barterly/src/providers.dart';
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';

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

/// Answers Dio requests from [routes] ("METHOD /path/") without a network.
/// Unmatched requests fail the test.
class FakeApi implements HttpClientAdapter {
  new([Map<String, Handler>? routes]) : routes = {...?routes};

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

/// Overrides that put the app on a fake API, in-memory tokens and fake sign-in.
List<Override> testOverrides({
  required FakeApi api,
  TokenStore? tokens,
  PhoneAuth? phoneAuth,
}) => [
  appConfigProvider.overrideWithValue(testConfig),
  httpAdapterProvider.overrideWithValue(api),
  tokenStoreProvider.overrideWithValue(tokens ?? MemoryTokenStore()),
  phoneAuthProvider.overrideWithValue(phoneAuth ?? FakePhoneAuth()),
];

/// Pumps the whole app on fakes and lets the session load.
Future<void> pumpApp(
  WidgetTester tester, {
  required FakeApi api,
  TokenStore? tokens,
  PhoneAuth? phoneAuth,
}) async {
  await tester.pumpWidget(
    ProviderScope(
      // Fail fast in tests instead of Riverpod's automatic retries.
      retry: (_, _) => null,
      overrides: testOverrides(api: api, tokens: tokens, phoneAuth: phoneAuth),
      child: const BarterlyApp(brandFonts: false),
    ),
  );
  await tester.pumpAndSettle();
}

const signedInTokens = Tokens(access: 'access-1', refresh: 'refresh-1');
