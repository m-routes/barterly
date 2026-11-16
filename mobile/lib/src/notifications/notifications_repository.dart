import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/notifications/notification_models.dart';
import 'package:dio/dio.dart';

/// The inbox, preferences and push devices (backend apps/notifications).
class NotificationsRepository {
  new(this._dio);

  final Dio _dio;

  Future<List<AppNotification>> inbox() => guardApi(() async {
    final response = await _dio.get<Map<String, Object?>>(
      '/api/v1/notifications/',
      queryParameters: {'page_size': 50},
    );
    return [
      for (final n in (response.data!['results'] as List?) ?? const [])
        if (n is Map<String, Object?>) AppNotification.fromJson(n),
    ];
  });

  Future<int> unreadCount() => guardApi(() async {
    final response = await _dio.get<Map<String, Object?>>(
      '/api/v1/notifications/unread-count/',
    );
    return (response.data!['unread'] as num?)?.toInt() ?? 0;
  });

  Future<void> markRead(String id, {bool fromPush = false}) =>
      guardApi(() async {
        await _dio.post<Object?>(
          '/api/v1/notifications/$id/read/',
          data: {'from_push': fromPush},
        );
      });

  Future<void> markAllRead() => guardApi(() async {
    await _dio.post<Object?>('/api/v1/notifications/read-all/');
  });

  Future<NotificationPrefs> preferences() => guardApi(() async {
    final response = await _dio.get<Map<String, Object?>>(
      '/api/v1/notifications/preferences/',
    );
    return NotificationPrefs.fromJson(response.data!);
  });

  Future<NotificationPrefs> savePreferences(
    NotificationPrefs prefs, {
    required List<(String, String, bool)> changes,
  }) => guardApi(() async {
    final response = await _dio.put<Map<String, Object?>>(
      '/api/v1/notifications/preferences/',
      data: {
        'locale': prefs.locale,
        'quiet_hours_enabled': prefs.quietHoursEnabled,
        'quiet_start': prefs.quietStart,
        'quiet_end': prefs.quietEnd,
        'changes': [
          for (final (eventType, channel, enabled) in changes)
            {'event_type': eventType, 'channel': channel, 'enabled': enabled},
        ],
      },
    );
    return NotificationPrefs.fromJson(response.data!);
  });

  Future<void> registerDevice(String token, {required String platform}) =>
      guardApi(() async {
        await _dio.post<Object?>(
          '/api/v1/notifications/devices/',
          data: {'token': token, 'platform': platform},
        );
      });

  Future<void> removeDevice(String token) => guardApi(() async {
    await _dio.post<Object?>(
      '/api/v1/notifications/devices/remove/',
      data: {'token': token},
    );
  });
}
