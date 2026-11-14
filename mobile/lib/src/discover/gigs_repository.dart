import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/discover/discovery_filters.dart';
import 'package:barterly/src/discover/gig.dart';
import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

@immutable
class SavedSearch {
  const new({
    required this.id,
    required this.name,
    required this.filters,
    this.alertsEnabled = true,
  });

  factory fromJson(Map<String, Object?> json) => SavedSearch(
    id: json['id']! as String,
    name: json['name'] as String? ?? '',
    filters: DiscoveryFilters.fromParams(
      (json['params'] as Map?)?.cast<String, Object?>() ?? const {},
    ),
    alertsEnabled: json['alerts_enabled'] as bool? ?? true,
  );

  final String id;
  final String name;
  final DiscoveryFilters filters;
  final bool alertsEnabled;
}

/// Talent discovery over the API.
class GigsRepository {
  new(this._dio);

  final Dio _dio;

  Future<GigPage> discover(DiscoveryFilters filters, {String? cursor}) =>
      guardApi(() async {
        final response = await _dio.get<Map<String, Object?>>(
          '/api/v1/gigs/',
          queryParameters: {...filters.toParams(), 'cursor': ?cursor},
        );
        return GigPage.fromJson(response.data!);
      });

  /// The full gig (description, screening questions) layered over [card].
  ///
  /// Returns [card] unchanged when the gig is no longer listed (404, e.g. it
  /// was paused or closed) or not readable (403), so the screen still works
  /// from the discover data.
  Future<Gig> detail(Gig card) async {
    try {
      return await guardApi(() async {
        final response = await _dio.get<Map<String, Object?>>(
          '/api/v1/gigs/${card.id}/public/',
        );
        return card.mergeDetail(response.data!);
      });
    } on ApiError catch (error) {
      if (error.status == 403 || error.status == 404) return card;
      rethrow;
    }
  }

  Future<List<SavedSearch>> savedSearches() => guardApi(() async {
    final response = await _dio.get<List<Object?>>(
      '/api/v1/gigs/saved-searches/',
    );
    return [
      for (final item in response.data!)
        SavedSearch.fromJson(item! as Map<String, Object?>),
    ];
  });

  Future<SavedSearch> saveSearch(String name, DiscoveryFilters filters) =>
      guardApi(() async {
        final params = filters.toParams();
        final response = await _dio.post<Map<String, Object?>>(
          '/api/v1/gigs/saved-searches/',
          data: {
            'name': name,
            // Saved searches store lists, not the query string's commas.
            'params': {
              for (final MapEntry(:key, :value) in params.entries)
                key: _listKeys.contains(key)
                    ? (value! as String).split(',')
                    : value,
            },
            'alerts_enabled': true,
          },
        );
        return SavedSearch.fromJson(response.data!);
      });

  Future<void> deleteSavedSearch(String id) =>
      guardApi(() => _dio.delete<void>('/api/v1/gigs/saved-searches/$id/'));

  static const _listKeys = {'compensation_model', 'role', 'stay_type'};
}
