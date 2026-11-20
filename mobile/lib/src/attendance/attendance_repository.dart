import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/attendance/attendance_models.dart';
import 'package:barterly/src/attendance/location.dart';
import 'package:barterly/src/platform/key_value_store.dart';
import 'package:dio/dio.dart';
import 'package:intl/intl.dart';

/// Check-in passes and hour logs over REST (backend apps/attendance). Passes are
/// kept on the device so they show without signal.
class AttendanceRepository {
  new(this._dio, this._store);

  final Dio _dio;
  final KeyValueStore _store;

  static String _key(String bookingId) => 'attendance.pass.$bookingId';

  Future<CheckInPass?> cachedPass(String bookingId) async {
    final json = await _store.readJson(_key(bookingId));
    if (json == null) return null;
    try {
      return CheckInPass.fromJson(json);
    } on Object {
      await _store.remove(_key(bookingId));
      return null;
    }
  }

  /// A fresh pass (sending [location] if there is one), kept for offline use.
  Future<CheckInPass> fetchPass(String bookingId, {Located? location}) =>
      guardApi(() async {
        final response = await _dio.post<Map<String, Object?>>(
          '/api/v1/bookings/$bookingId/attendance/pass/',
          data: {'location': location?.toJson()},
        );
        final pass = CheckInPass.fromJson(response.data!);
        await _store.writeJson(_key(bookingId), pass.toJson());
        return pass;
      });

  Future<void> forgetPass(String bookingId) => _store.remove(_key(bookingId));

  static final _day = DateFormat('yyyy-MM-dd');

  Future<HoursWeek> week(String bookingId, DateTime day) => guardApi(() async {
    final response = await _dio.get<Map<String, Object?>>(
      '/api/v1/bookings/$bookingId/hours/',
      queryParameters: {'week': _day.format(day)},
    );
    return HoursWeek.fromJson(response.data!);
  });

  Future<HoursCheck> check(
    String bookingId, {
    required DateTime day,
    required int minutes,
  }) => guardApi(() async {
    final response = await _dio.post<Map<String, Object?>>(
      '/api/v1/bookings/$bookingId/hours/check/',
      data: {'day': _day.format(day), 'minutes': minutes},
    );
    return HoursCheck.fromJson(response.data!);
  });

  /// Saves the day's hours. Returns the warnings that came with it.
  Future<List<String>> log(
    String bookingId, {
    required DateTime day,
    required int minutes,
    String note = '',
  }) => guardApi(() async {
    final response = await _dio.post<Map<String, Object?>>(
      '/api/v1/bookings/$bookingId/hours/',
      data: {'day': _day.format(day), 'minutes': minutes, 'note': note},
    );
    final check = response.data!['check'];
    return check is Map<String, Object?>
        ? HoursCheck.fromJson(check).warnings
        : const [];
  });
}
