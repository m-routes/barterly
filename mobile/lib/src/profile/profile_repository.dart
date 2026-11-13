import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/profile/talent_profile.dart';
import 'package:dio/dio.dart';

/// The talent profile and the skills list, over the API.
class ProfileRepository {
  new(this._dio);

  final Dio _dio;

  /// The saved profile, or null if this person hasn't started one.
  Future<TalentProfile?> fetchTalentProfile() async {
    try {
      return await guardApi(() async {
        final response = await _dio.get<Map<String, Object?>>(
          '/api/v1/profiles/talent/me/',
        );
        return TalentProfile.fromJson(response.data!);
      });
    } on ApiError catch (error) {
      if (error.code == 'profile_not_found') return null;
      rethrow;
    }
  }

  /// Creates the profile (first save) or updates it.
  Future<TalentProfile> saveTalentProfile(TalentProfile profile) =>
      guardApi(() async {
        final response = await _dio.patch<Map<String, Object?>>(
          '/api/v1/profiles/talent/me/',
          data: profile.toJson(),
        );
        return TalentProfile.fromJson(response.data!);
      });

  Future<List<Skill>> skills() => guardApi(() async {
    final response = await _dio.get<List<Object?>>('/api/v1/profiles/skills/');
    return [
      for (final item in response.data!)
        Skill.fromJson(item! as Map<String, Object?>),
    ];
  });
}
