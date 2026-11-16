import 'dart:async';

import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';

/// A push someone tapped: the notification and the app route it points at.
@immutable
class OpenedPush {
  const new({required this.notificationId, required this.path});

  /// From FCM's data payload (backend apps/notifications/channels/fcm.py).
  static OpenedPush? fromData(Map<String, Object?> data) {
    final path = data['path'];
    if (path is! String || !path.startsWith('/')) return null;
    return OpenedPush(
      notificationId: data['notification_id'] as String? ?? '',
      path: path,
    );
  }

  final String notificationId;
  final String path;
}

/// Push messaging, behind an interface so tests and builds without Firebase
/// use [NoPushMessaging].
abstract interface class PushMessaging {
  /// Asks to show notifications; false when the person said no.
  Future<bool> requestPermission();

  Future<String?> token();

  Stream<String> get tokenRefreshes;

  /// Pushes tapped while the app was running or in the background.
  Stream<OpenedPush> get opened;

  /// The push that launched the app, if one did.
  Future<OpenedPush?> launchedFrom();

  Future<void> deleteToken();

  String get platform;
}

class NoPushMessaging implements PushMessaging {
  const new();

  @override
  Future<bool> requestPermission() async => false;

  @override
  Future<String?> token() async => null;

  @override
  Stream<String> get tokenRefreshes => const Stream.empty();

  @override
  Stream<OpenedPush> get opened => const Stream.empty();

  @override
  Future<OpenedPush?> launchedFrom() async => null;

  @override
  Future<void> deleteToken() async {}

  @override
  String get platform => defaultTargetPlatform.name;
}

/// Uses FCM registration tokens, which the API sends to with the HTTP v1 API
/// (firebase-admin). firebase_messaging 17 deprecates them in favour of
/// installation IDs (register()/onRegistered); move both sides together.
class FirebasePushMessaging implements PushMessaging {
  FirebaseMessaging get _fcm => FirebaseMessaging.instance;

  @override
  Future<bool> requestPermission() async {
    final settings = await _fcm.requestPermission();
    return settings.authorizationStatus == AuthorizationStatus.authorized ||
        settings.authorizationStatus == AuthorizationStatus.provisional;
  }

  @override
  // ignore: deprecated_member_use (see the class comment)
  Future<String?> token() => _fcm.getToken();

  @override
  // ignore: deprecated_member_use (see the class comment)
  Stream<String> get tokenRefreshes => _fcm.onTokenRefresh;

  @override
  Stream<OpenedPush> get opened => FirebaseMessaging.onMessageOpenedApp
      .map((m) => OpenedPush.fromData(m.data))
      .where((p) => p != null)
      .cast<OpenedPush>();

  @override
  Future<OpenedPush?> launchedFrom() async {
    final message = await _fcm.getInitialMessage();
    return message == null ? null : OpenedPush.fromData(message.data);
  }

  @override
  // ignore: deprecated_member_use (see the class comment)
  Future<void> deleteToken() => _fcm.deleteToken();

  @override
  String get platform => switch (defaultTargetPlatform) {
    TargetPlatform.iOS => 'ios',
    _ => 'android',
  };
}
