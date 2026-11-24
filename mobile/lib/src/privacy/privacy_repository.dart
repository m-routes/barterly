import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/privacy/legal.dart';
import 'package:barterly/src/privacy/privacy_models.dart';
import 'package:dio/dio.dart';

/// Consents, data export, corrections and account deletion
/// (backend apps/privacy/views.py).
class PrivacyRepository {
  new(this._dio);

  final Dio _dio;

  Future<List<Consent>> consents() => guardApi(() async {
    final response = await _dio.get<List<Object?>>('/api/v1/privacy/consents/');
    return _consents(response.data!);
  });

  /// Gives (with the version shown) or withdraws one consent. Same call both
  /// ways, so withdrawing is as easy as giving.
  Future<List<Consent>> setConsent(String purpose, {required bool granted}) =>
      guardApi(() async {
        final response = await _dio.post<List<Object?>>(
          '/api/v1/privacy/consents/',
          data: {
            'purpose': purpose,
            'granted': granted,
            if (granted) 'version': legalVersion,
            'source': 'mobile',
          },
        );
        return _consents(response.data!);
      });

  Future<List<DataExport>> exports() => guardApi(() async {
    final response = await _dio.get<Map<String, Object?>>(
      '/api/v1/privacy/exports/',
    );
    return [
      for (final e in response.data!['results']! as List<Object?>)
        DataExport.fromJson(e! as Map<String, Object?>),
    ];
  });

  Future<DataExport> createExport() => guardApi(() async {
    final response = await _dio.post<Map<String, Object?>>(
      '/api/v1/privacy/exports/',
    );
    return DataExport.fromJson(response.data!);
  });

  /// A signed download link that works for a few minutes.
  Future<Uri> exportLink(String exportId) => guardApi(() async {
    final response = await _dio.post<Map<String, Object?>>(
      '/api/v1/privacy/exports/$exportId/link/',
    );
    return Uri.parse(response.data!['url']! as String);
  });

  Future<void> requestCorrection({
    required String field,
    required String correctValue,
    String note = '',
  }) => guardApi(() async {
    await _dio.post<Object?>(
      '/api/v1/privacy/corrections/',
      data: {'field': field, 'correct_value': correctValue, 'note': note},
    );
  });

  Future<DeletionState> deletion() => guardApi(() async {
    final response = await _dio.get<Map<String, Object?>>(
      '/api/v1/privacy/deletion/',
    );
    return DeletionState.fromJson(response.data!);
  });

  Future<DeletionState> requestDeletion() => guardApi(() async {
    final response = await _dio.post<Map<String, Object?>>(
      '/api/v1/privacy/deletion/',
      data: {'confirm': true},
    );
    return DeletionState.fromJson(response.data!);
  });

  Future<void> cancelDeletion() => guardApi(() async {
    await _dio.delete<Object?>('/api/v1/privacy/deletion/');
  });

  List<Consent> _consents(List<Object?> rows) => [
    for (final row in rows) Consent.fromJson(row! as Map<String, Object?>),
  ];
}
