import 'dart:async';

import 'package:barterly/src/analytics/events.dart';
import 'package:barterly/src/providers.dart';
import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Product analytics, only with consent (docs/beta/analytics.md).
///
/// Nothing leaves the phone until we know the person said yes to "Product
/// analytics" in Privacy and your data; withdrawing stops sending at once and
/// the server deletes what it had. Events are sent in batches of [batchSize],
/// and when the app goes to the background. No timers: nothing runs while the
/// app is idle.
class Analytics {
  new(this._dio, {this.batchSize = 10});

  final Dio _dio;
  final int batchSize;

  bool? _consent; // null: not checked yet
  final List<Map<String, Object?>> _queue = [];
  Future<void>? _sending;

  bool? get consent => _consent;
  int get queued => _queue.length;

  /// Privacy and your data calls this when the person changes their answer.
  void setConsent({required bool granted}) {
    _consent = granted;
    if (!granted) _queue.clear();
  }

  void reset() {
    _consent = null;
    _queue.clear();
  }

  void track(String name, [Map<String, Object?> props = const {}]) {
    assert(eventNames.contains(name), 'Unknown analytics event $name');
    if (_consent == false) return;
    _queue.add({
      'name': name,
      'occurred_at': DateTime.now().toUtc().toIso8601String(),
      'props': props,
    });
    if (_queue.length > 100) _queue.removeRange(0, _queue.length - 100);
    if (_queue.length >= batchSize) unawaited(flush());
  }

  Future<void> flush() =>
      _sending ??= _send().whenComplete(() => _sending = null);

  Future<void> _send() async {
    if (_queue.isEmpty) return;
    if (!await _allowed()) {
      _queue.clear();
      return;
    }
    final batch = _queue.take(50).toList();
    _queue.removeRange(0, batch.length);
    try {
      final response = await _dio.post<Map<String, Object?>>(
        '/api/v1/analytics/events/',
        data: {
          'platform': platformName,
          'app_version': appVersion,
          'events': batch,
        },
      );
      if (response.data?['consent'] == false) setConsent(granted: false);
    } on DioException {
      // Analytics never gets in the way: drop the batch.
    }
  }

  Future<bool> _allowed() async {
    if (_consent != null) return _consent!;
    try {
      final response = await _dio.get<List<Object?>>(
        '/api/v1/privacy/consents/',
      );
      _consent = (response.data ?? const []).any(
        (c) => c is Map && c['purpose'] == 'analytics' && c['granted'] == true,
      );
    } on DioException {
      return false; // try again next time
    }
    return _consent!;
  }
}

/// "android" or "ios", as the API expects.
String get platformName => switch (defaultTargetPlatform) {
  TargetPlatform.iOS => 'ios',
  _ => 'android',
};

/// The build's version, from `--dart-define=APP_VERSION=...` (tool/build_release.sh).
const appVersion = String.fromEnvironment('APP_VERSION');

final analyticsProvider = Provider<Analytics>((ref) {
  final analytics = Analytics(ref.watch(dioProvider));
  final lifecycle = AppLifecycleListener(
    onPause: () => unawaited(analytics.flush()),
  );
  ref.onDispose(lifecycle.dispose);
  return analytics;
});
