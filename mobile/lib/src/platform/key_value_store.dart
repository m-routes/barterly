import 'dart:convert';

import 'package:barterly/src/api/token_store.dart' show SecureTokenStore;
import 'package:shared_preferences/shared_preferences.dart';

/// Small JSON documents kept on the device: the offline discover page and the
/// queue of applications waiting for a network. Not for secrets (tokens live in
/// [SecureTokenStore]).
abstract interface class KeyValueStore {
  Future<Map<String, Object?>?> readJson(String key);
  Future<void> writeJson(String key, Map<String, Object?> value);
  Future<void> remove(String key);
}

class SharedPrefsStore implements KeyValueStore {
  new([SharedPreferencesAsync? prefs])
    : _prefs = prefs ?? SharedPreferencesAsync();

  final SharedPreferencesAsync _prefs;

  @override
  Future<Map<String, Object?>?> readJson(String key) async {
    final raw = await _prefs.getString(key);
    if (raw == null) return null;
    try {
      final decoded = jsonDecode(raw);
      return decoded is Map<String, Object?> ? decoded : null;
    } on FormatException {
      // A corrupt entry is dropped rather than crashing the screen.
      await _prefs.remove(key);
      return null;
    }
  }

  @override
  Future<void> writeJson(String key, Map<String, Object?> value) =>
      _prefs.setString(key, jsonEncode(value));

  @override
  Future<void> remove(String key) => _prefs.remove(key);
}

/// For tests, and the fallback when nothing should persist.
class MemoryKeyValueStore implements KeyValueStore {
  new([Map<String, Map<String, Object?>>? initial]) : data = {...?initial};

  final Map<String, Map<String, Object?>> data;

  @override
  Future<Map<String, Object?>?> readJson(String key) async {
    final value = data[key];
    // Round-trip through JSON so callers can't share mutable state.
    return value == null
        ? null
        : jsonDecode(jsonEncode(value)) as Map<String, Object?>;
  }

  @override
  Future<void> writeJson(String key, Map<String, Object?> value) async =>
      data[key] = jsonDecode(jsonEncode(value)) as Map<String, Object?>;

  @override
  Future<void> remove(String key) async => data.remove(key);
}
