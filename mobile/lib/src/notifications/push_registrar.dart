import 'dart:async';

import 'package:barterly/src/apply/outbox.dart' show myApplicationsProvider;
import 'package:barterly/src/notifications/push.dart';
import 'package:barterly/src/providers.dart';
import 'package:barterly/src/router.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

/// Ties push to the session: once signed in, ask permission, register the
/// device's token (and its refreshes), and handle pushes in every state:
/// - open (foreground): the system shows nothing, so a banner does, with Open;
/// - in the background: the system shows it; tapping opens the app here;
/// - not running (terminated): tapping launches the app, then [start] opens it.
/// Opening goes to the screen the push points at and marks it read. On
/// sign-out the device is removed first.
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
      ..add(_push.received.listen(_show))
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

  void _show(ReceivedPush push) {
    // Whatever it was about may have changed: fetch again where it shows.
    _ref
      ..invalidate(unreadCountProvider)
      ..invalidate(myApplicationsProvider)
      ..invalidate(applicationDetailProvider);
    final messenger = _ref.read(scaffoldMessengerKeyProvider).currentState;
    if (messenger == null) return;
    final target = push.open;
    messenger
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(
            [push.title, push.body].where((t) => t.isNotEmpty).join('\n'),
          ),
          duration: const Duration(seconds: 6),
          action: target == null
              ? null
              : SnackBarAction(
                  label: 'Open',
                  onPressed: () => unawaited(open(target)),
                ),
        ),
      );
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
