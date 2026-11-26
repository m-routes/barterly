import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/support/support_models.dart';
import 'package:dio/dio.dart';

/// Help and feedback (backend apps/support/views.py).
class SupportRepository {
  new(this._dio);

  final Dio _dio;

  Future<List<SupportTicket>> mine() => guardApi(() async {
    final response = await _dio.get<Object?>('/api/v1/support/tickets/');
    final data = response.data;
    final rows = data is Map
        ? data['results']! as List<Object?>
        : data! as List<Object?>;
    return [
      for (final t in rows) SupportTicket.fromJson(t! as Map<String, Object?>),
    ];
  });

  Future<SupportTicket> open({
    required String kind,
    required String subject,
    required String body,
    required String platform,
    String? bookingId,
    String screen = 'profile/help',
  }) => guardApi(() async {
    final response = await _dio.post<Map<String, Object?>>(
      '/api/v1/support/tickets/',
      data: {
        'kind': kind,
        'subject': subject,
        'body': body,
        'booking_id': ?bookingId,
        'screen': screen,
        'platform': platform,
      },
    );
    return SupportTicket.fromJson(response.data!);
  });

  Future<SupportTicket> get(String id) => guardApi(() async {
    final response = await _dio.get<Map<String, Object?>>(
      '/api/v1/support/tickets/$id/',
    );
    return SupportTicket.fromJson(response.data!);
  });

  Future<SupportTicket> reply(String id, String body) => guardApi(() async {
    final response = await _dio.post<Map<String, Object?>>(
      '/api/v1/support/tickets/$id/messages/',
      data: {'body': body},
    );
    return SupportTicket.fromJson(response.data!);
  });
}
