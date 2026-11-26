import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/api/token_store.dart';
import 'package:barterly/src/auth/user.dart';
import 'package:barterly/src/privacy/legal.dart';
import 'package:dio/dio.dart';

/// Sign-in, the current user and role choice, over the API.
class AuthRepository {
  new({required this._dio, required this._tokens});

  final Dio _dio;
  final TokenStore _tokens;

  Future<bool> get hasSession async => await _tokens.read() != null;

  /// Trades a Firebase ID token for the API's tokens, and stores them.
  Future<User> exchange(String firebaseIdToken) => guardApi(() async {
    final response = await _dio.post<Map<String, Object?>>(
      '/api/v1/auth/exchange/',
      data: {'id_token': firebaseIdToken},
    );
    final body = response.data!;
    await _tokens.write(
      Tokens(
        access: body['access']! as String,
        refresh: body['refresh']! as String,
      ),
    );
    return User.fromJson(body['user']! as Map<String, Object?>);
  });

  Future<User> me() => guardApi(() async {
    final response = await _dio.get<Map<String, Object?>>('/api/v1/me/');
    return User.fromJson(response.data!);
  });

  /// Sets the role once. Talent use this app; vendors use the web console.
  /// The person has declared they are 18 or older and accepted the terms and
  /// the privacy policy shown ([legalVersion]); each is recorded separately.
  ///
  /// During the closed beta the API may need an [inviteCode]
  /// (GET /api/v1/beta/ says so); without one it answers `invite_required`.
  Future<User> chooseTalentRole({String? inviteCode}) => guardApi(() async {
    final response = await _dio.post<Map<String, Object?>>(
      '/api/v1/me/role/',
      data: {
        'role': 'talent',
        'confirm_adult': true,
        'terms_version': legalVersion,
        'privacy_version': legalVersion,
        'source': 'mobile',
        if (inviteCode != null && inviteCode.isNotEmpty)
          'invite_code': inviteCode,
      },
    );
    return User.fromJson(response.data!);
  });

  /// Which roles need an invite code right now (the closed beta's rules).
  Future<List<String>> inviteRoles() => guardApi(() async {
    final response = await _dio.get<Map<String, Object?>>('/api/v1/beta/');
    return [
      for (final r
          in (response.data?['invite_required_for'] as List<Object?>?) ??
              const [])
        r! as String,
    ];
  });

  /// Blacklists the refresh token if the API is reachable; always forgets it.
  Future<void> signOut() async {
    final tokens = await _tokens.read();
    try {
      if (tokens != null) {
        await _dio.post<void>(
          '/api/v1/auth/logout/',
          data: {'refresh': tokens.refresh},
        );
      }
    } on DioException {
      // Signing out of this device matters more than telling the server.
    } finally {
      await _tokens.clear();
    }
  }
}
