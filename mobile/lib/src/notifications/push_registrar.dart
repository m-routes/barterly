import 'dart:async';

import 'package:barterly/src/notifications/push.dart';
import 'package:barterly/src/providers.dart';
import 'package:barterly/src/router.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Ties push to the session: once signed in, ask permission, register the
/// device's token (and its refreshes), and open the screen a tapped push
/// points at, marking it read. On sign-out the device is removed first.
class PushRegistrar {
  new(this._ref);

  final Ref _ref;
  final _subscriptions = <StreamSubscription<Object?>>[];
  String? _token;
  bool _started = false;

  PushMessaging get _push => _ref.read(pushMessagingProvider);

  Future<void> start() async {
    if (_started) return;
    _started = true;
    _subscriptions
      ..add(_push.opened.listen((p) => unawaited(open(p))))
      ..add(_push.tokenRefreshes.listen((t) => unawaited(_register(t))));
    try {
      if (await _push.requestPermission()) {
        final token = await _push.token();
        if (token != null) await _register(token);
      }
      final launched = await _push.launchedFrom();
      if (launched != null) await open(launched);
    } on Object catch (error, stack) {
      await _ref
          .read(crashReporterProvider)
          .report(error, stack, context: 'push');
    }
  }

  Future<void> _register(String token) async {
    _token = token;
    try {
      await _ref
          .read(notificationsRepositoryProvider)
          .registerDevice(token, platform: _push.platform);
    } on Object {
      // Registering again on the next start or token refresh is enough.
    }
  }

  /// Go where the push points, and count it as read.
  Future<void> open(OpenedPush push) async {
    _ref.read(routerProvider).go(push.path);
    if (push.notificationId.isEmpty) return;
    try {
      await _ref
          .read(notificationsRepositoryProvider)
          .markRead(push.notificationId, fromPush: true);
    } on Object {
      // The screen opened; the read mark can wait.
    }
    _ref.invalidate(unreadCountProvider);
  }

  /// Before signing out: this device should stop getting this person's pushes.
  Future<void> stop() async {
    final token = _token;
    _token = null;
    _started = false;
    final subscriptions = [..._subscriptions];
    _subscriptions.clear();
    try {
      if (token != null) {
        await _ref.read(notificationsRepositoryProvider).removeDevice(token);
        await _push.deleteToken();
      }
    } on Object {
      // Signing out goes ahead regardless.
    } finally {
      for (final s in subscriptions) {
        unawaited(s.cancel());
      }
    }
  }
}
