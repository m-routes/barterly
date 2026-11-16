import 'package:barterly/src/agreements/agreement_models.dart';
import 'package:barterly/src/api/api_error.dart';
import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

/// Offers and agreements over REST (backend apps/offers, apps/agreements).
class AgreementsRepository {
  new(this._dio);

  final Dio _dio;

  Future<OfferThread> offers(String applicationId) => guardApi(() async {
    final response = await _dio.get<Map<String, Object?>>(
      '/api/v1/applications/$applicationId/offers/',
    );
    return OfferThread.fromJson(response.data!);
  });

  /// Books the slot. Returns the new booking's id.
  Future<String> accept(String offerId) => guardApi(() async {
    final response = await _dio.post<Map<String, Object?>>(
      '/api/v1/offers/$offerId/accept/',
    );
    return response.data!['booking']! as String;
  });

  Future<OfferThread> decline(String offerId, {String reason = ''}) =>
      guardApi(() async {
        final response = await _dio.post<Map<String, Object?>>(
          '/api/v1/offers/$offerId/decline/',
          data: {'reason': reason},
        );
        return OfferThread.fromJson(response.data!);
      });

  Future<OfferThread> counter(
    String offerId, {
    required Map<String, Object?> changes,
    String message = '',
  }) => guardApi(() async {
    final response = await _dio.post<Map<String, Object?>>(
      '/api/v1/offers/$offerId/counter/',
      data: {'changes': changes, 'message': message},
    );
    return OfferThread.fromJson(response.data!);
  });

  Future<Agreement> agreement(String agreementId) => guardApi(() async {
    final response = await _dio.get<Map<String, Object?>>(
      '/api/v1/agreements/$agreementId/',
    );
    return Agreement.fromJson(response.data!);
  });

  Future<Agreement> agreementForBooking(String bookingId) => guardApi(() async {
    final response = await _dio.get<Map<String, Object?>>(
      '/api/v1/bookings/$bookingId/agreement/',
    );
    return Agreement.fromJson(response.data!);
  });

  /// A short-lived link to the version's PDF.
  Future<Uri> pdfLink(String versionId) => guardApi(() async {
    final response = await _dio.get<Map<String, Object?>>(
      '/api/v1/agreement-versions/$versionId/pdf/',
    );
    return Uri.parse(response.data!['url']! as String);
  });

  Future<SignChallenge> challenge(String versionId) => guardApi(() async {
    final response = await _dio.get<Map<String, Object?>>(
      '/api/v1/agreement-versions/$versionId/sign/',
    );
    return SignChallenge.fromJson(response.data!);
  });

  Future<Agreement> sign(
    String versionId, {
    required String documentSha256,
    required String otpToken,
  }) => guardApi(() async {
    final response = await _dio.post<Map<String, Object?>>(
      '/api/v1/agreement-versions/$versionId/sign/',
      data: {
        'consent': true,
        'document_sha256': documentSha256,
        'otp_token': otpToken,
      },
      // Kept with the signature, with the IP address and time.
      options: Options(
        headers: {
          'X-Client-Device': 'Barterly app (${defaultTargetPlatform.name})',
        },
      ),
    );
    return Agreement.fromJson(response.data!);
  });

  Future<Agreement> declineChange(String versionId, {String reason = ''}) =>
      guardApi(() async {
        final response = await _dio.post<Map<String, Object?>>(
          '/api/v1/agreement-versions/$versionId/decline/',
          data: {'reason': reason},
        );
        return Agreement.fromJson(response.data!);
      });
}
