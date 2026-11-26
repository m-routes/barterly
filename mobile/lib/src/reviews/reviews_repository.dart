import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/reviews/review_models.dart';
import 'package:dio/dio.dart';

/// Reviews and reputation over REST (backend apps/reviews).
class ReviewsRepository {
  new(this._dio);

  final Dio _dio;

  Future<BookingReviews> forBooking(String bookingId) => guardApi(() async {
    final response = await _dio.get<Map<String, Object?>>(
      '/api/v1/bookings/$bookingId/reviews/',
    );
    return BookingReviews.fromJson(response.data!);
  });

  Future<void> submit(
    String bookingId, {
    required int rating,
    required Map<String, int> scores,
    required String text,
  }) => guardApi(() async {
    await _dio.post<Object?>(
      '/api/v1/bookings/$bookingId/reviews/',
      data: {'rating': rating, ...scores, 'text': text},
    );
  });

  Future<void> reply(String reviewId, String text) => guardApi(() async {
    await _dio.post<Object?>(
      '/api/v1/reviews/$reviewId/reply/',
      data: {'text': text},
    );
  });

  Future<Reputation> reputation(String userId) => guardApi(() async {
    final response = await _dio.get<Map<String, Object?>>(
      '/api/v1/users/$userId/reputation/',
    );
    return Reputation.fromJson(
      (response.data!['talent'] as Map<String, Object?>?) ?? const {},
    );
  });

  Future<List<StayReview>> aboutMe(String userId) => guardApi(() async {
    final response = await _dio.get<Map<String, Object?>>(
      '/api/v1/users/$userId/reviews/',
      queryParameters: {'side': 'talent'},
    );
    return [
      for (final r in (response.data!['results'] as List?) ?? const [])
        if (r is Map<String, Object?>) StayReview.fromJson(r),
    ];
  });
}
