import 'package:flutter/foundation.dart';

/// One inbox item (backend apps/notifications/serializers.py).
@immutable
class AppNotification {
  const new({
    required this.id,
    required this.kind,
    required this.title,
    required this.body,
    required this.createdAt,
    this.appPath = '',
    this.urgent = false,
    this.read = false,
  });

  factory fromJson(Map<String, Object?> json) => AppNotification(
    id: json['id']! as String,
    kind: json['kind'] as String? ?? '',
    title: json['title'] as String? ?? '',
    body: json['body'] as String? ?? '',
    appPath: json['app_path'] as String? ?? '',
    urgent: json['urgent'] as bool? ?? false,
    read: json['read'] as bool? ?? false,
    createdAt:
        DateTime.tryParse(json['created_at'] as String? ?? '') ??
        DateTime.fromMillisecondsSinceEpoch(0),
  );

  final String id;
  final String kind;
  final String title;
  final String body;
  final String appPath;
  final bool urgent;
  final bool read;
  final DateTime createdAt;

  AppNotification markedRead() => AppNotification(
    id: id,
    kind: kind,
    title: title,
    body: body,
    appPath: appPath,
    urgent: urgent,
    read: true,
    createdAt: createdAt,
  );
}

const channelLabels = {
  'in_app': 'In the app',
  'push': 'Push',
  'email': 'Email',
  'sms': 'SMS',
  'whatsapp': 'WhatsApp',
};

@immutable
class ChannelSetting {
  const new({required this.enabled, this.locked = false});

  final bool enabled;
  final bool locked;
}

@immutable
class EventTypeSetting {
  const new({
    required this.key,
    required this.label,
    required this.channels,
    this.urgent = false,
  });

  factory fromJson(Map<String, Object?> json) => EventTypeSetting(
    key: json['key']! as String,
    label: json['label'] as String? ?? '',
    urgent: json['urgent'] as bool? ?? false,
    channels: {
      for (final MapEntry(:key, :value)
          in ((json['channels'] as Map?) ?? const {}).entries)
        if (value is Map)
          '$key': ChannelSetting(
            enabled: value['enabled'] as bool? ?? false,
            locked: value['locked'] as bool? ?? false,
          ),
    },
  );

  final String key;
  final String label;
  final bool urgent;
  final Map<String, ChannelSetting> channels;

  EventTypeSetting with_(String channel, {required bool enabled}) =>
      EventTypeSetting(
        key: key,
        label: label,
        urgent: urgent,
        channels: {
          ...channels,
          channel: ChannelSetting(
            enabled: enabled,
            locked: channels[channel]?.locked ?? false,
          ),
        },
      );
}

/// Language, quiet hours (India time) and channels per event type.
@immutable
class NotificationPrefs {
  const new({
    required this.locale,
    required this.quietHoursEnabled,
    required this.quietStart,
    required this.quietEnd,
    required this.channelsAvailable,
    required this.eventTypes,
  });

  factory fromJson(Map<String, Object?> json) => NotificationPrefs(
    locale: json['locale'] as String? ?? 'en',
    quietHoursEnabled: json['quiet_hours_enabled'] as bool? ?? true,
    quietStart: json['quiet_start'] as String? ?? '22:00',
    quietEnd: json['quiet_end'] as String? ?? '08:00',
    channelsAvailable: [
      for (final c in (json['channels_available'] as List?) ?? const []) '$c',
    ],
    eventTypes: [
      for (final t in (json['event_types'] as List?) ?? const [])
        if (t is Map<String, Object?>) EventTypeSetting.fromJson(t),
    ],
  );

  final String locale;
  final bool quietHoursEnabled;
  final String quietStart;
  final String quietEnd;
  final List<String> channelsAvailable;
  final List<EventTypeSetting> eventTypes;

  NotificationPrefs copyWith({
    String? locale,
    bool? quietHoursEnabled,
    String? quietStart,
    String? quietEnd,
    List<EventTypeSetting>? eventTypes,
  }) => NotificationPrefs(
    locale: locale ?? this.locale,
    quietHoursEnabled: quietHoursEnabled ?? this.quietHoursEnabled,
    quietStart: quietStart ?? this.quietStart,
    quietEnd: quietEnd ?? this.quietEnd,
    channelsAvailable: channelsAvailable,
    eventTypes: eventTypes ?? this.eventTypes,
  );
}
