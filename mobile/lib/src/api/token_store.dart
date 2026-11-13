import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

@immutable
class Tokens {
  const new({required this.access, required this.refresh});

  final String access;
  final String refresh;
}

/// Where the API's JWTs live between launches.
abstract interface class TokenStore {
  Future<Tokens?> read();
  Future<void> write(Tokens tokens);
  Future<void> clear();
}

/// Keychain on iOS, encrypted shared preferences on Android.
class SecureTokenStore implements TokenStore {
  new([FlutterSecureStorage? storage])
    : _storage =
          storage ??
          const FlutterSecureStorage(
            // Tokens stay on this device: not in iCloud Keychain or backups.
            iOptions: IOSOptions(
              accessibility: KeychainAccessibility.first_unlock_this_device,
            ),
          );

  static const _accessKey = 'barterly.access';
  static const _refreshKey = 'barterly.refresh';

  final FlutterSecureStorage _storage;

  @override
  Future<Tokens?> read() async {
    final access = await _storage.read(key: _accessKey);
    final refresh = await _storage.read(key: _refreshKey);
    if (access == null || refresh == null) return null;
    return Tokens(access: access, refresh: refresh);
  }

  @override
  Future<void> write(Tokens tokens) async {
    await _storage.write(key: _accessKey, value: tokens.access);
    await _storage.write(key: _refreshKey, value: tokens.refresh);
  }

  @override
  Future<void> clear() async {
    await _storage.delete(key: _accessKey);
    await _storage.delete(key: _refreshKey);
  }
}

/// For tests and previews.
class MemoryTokenStore implements TokenStore {
  new([this._tokens]);

  Tokens? _tokens;

  @override
  Future<Tokens?> read() async => _tokens;

  @override
  Future<void> write(Tokens tokens) async => _tokens = tokens;

  @override
  Future<void> clear() async => _tokens = null;
}
