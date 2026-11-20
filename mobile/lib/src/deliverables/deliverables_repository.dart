import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/deliverables/deliverable_models.dart';
import 'package:dio/dio.dart';

/// Deliverables over REST (backend apps/deliverables).
class DeliverablesRepository {
  new(this._dio);

  final Dio _dio;

  Future<List<Deliverable>> forBooking(String bookingId) => guardApi(() async {
    final response = await _dio.get<List<Object?>>(
      '/api/v1/bookings/$bookingId/deliverables/items/',
    );
    return [
      for (final d in response.data ?? const [])
        if (d is Map<String, Object?>) Deliverable.fromJson(d),
    ];
  });

  Future<void> submit(
    String deliverableId, {
    String postUrl = '',
    List<String> fileIds = const [],
    String note = '',
    bool disclosureConfirmed = false,
  }) => guardApi(() async {
    await _dio.post<Object?>(
      '/api/v1/deliverables/items/$deliverableId/submit/',
      data: {
        'post_url': postUrl,
        'file_ids': fileIds,
        'note': note,
        'disclosure_confirmed': disclosureConfirmed,
      },
    );
  });

  Future<void> reportStats(
    String deliverableId, {
    required String screenshotId,
    int? views,
    int? likes,
    int? comments,
  }) => guardApi(() async {
    await _dio.post<Object?>(
      '/api/v1/deliverables/items/$deliverableId/stats/',
      data: {
        'views': views,
        'likes': likes,
        'comments': comments,
        'screenshot_id': screenshotId,
      },
    );
  });
}
