import 'package:barterly/src/discover/gig.dart';
import 'package:barterly/src/pay_model.dart';
import 'package:barterly/src/profile/talent_profile.dart' show formatDate;
import 'package:flutter/foundation.dart';

/// How the API can order results (backend apps/discovery/filters.py Sort).
enum GigSort {
  bestFit('best_fit', 'Best fit', 'Ranked by fit with your profile'),
  newest('newest', 'Newest', 'Newest first'),
  startDate('start_date', 'Starting soonest', 'Starting soonest first'),
  distance('distance', 'Nearest', 'Nearest first');

  new(this.value, this.label, this.caption);

  final String value;
  final String label;
  final String caption;

  static GigSort parse(String? value) =>
      values.where((s) => s.value == value).firstOrNull ?? bestFit;
}

/// A point to measure distance from. The API needs one for [GigSort.distance]
/// and for a radius.
@immutable
class SearchPoint {
  const new({required this.latitude, required this.longitude, this.label = ''});

  final double latitude;
  final double longitude;
  final String label;
}

/// Everything the talent can filter discover by. Immutable; the screens build
/// new values with [copyWith].
@immutable
class DiscoveryFilters {
  const new({
    this.payModels = const {},
    this.roles = const {},
    this.stayTypes = const {},
    this.city = '',
    this.query = '',
    this.point,
    this.radiusKm,
    this.startFrom,
    this.startTo,
    this.womenFriendly = false,
    this.verifiedHosts = false,
    this.minStay,
    this.sort = GigSort.bestFit,
  });

  factory fromParams(Map<String, Object?> params) {
    List<String> list(String key) => switch (params[key]) {
      final List<Object?> l => l.whereType<String>().toList(),
      final String s => s.split(',').where((p) => p.isNotEmpty).toList(),
      _ => const [],
    };
    DateTime? date(String key) => params[key] is String
        ? DateTime.tryParse(params[key]! as String)
        : null;
    final lat = params['latitude'];
    final lng = params['longitude'];
    return DiscoveryFilters(
      payModels: {...list('compensation_model').map(parsePayModel).nonNulls},
      roles: {...list('role').map(RoleTemplate.parse).nonNulls},
      stayTypes: {...list('stay_type').map(StayType.parse).nonNulls},
      city: params['city'] as String? ?? '',
      query: params['q'] as String? ?? '',
      point: lat is num && lng is num
          ? SearchPoint(latitude: lat.toDouble(), longitude: lng.toDouble())
          : null,
      radiusKm: (params['radius_km'] as num?)?.toDouble(),
      startFrom: date('start_from'),
      startTo: date('start_to'),
      womenFriendly: params['women_friendly'] == true,
      verifiedHosts: params['verified_hosts'] == true,
      minStay: (params['min_stay'] as num?)?.toInt(),
      sort: GigSort.parse(params['sort'] as String?),
    );
  }

  final Set<PayModel> payModels;
  final Set<RoleTemplate> roles;
  final Set<StayType> stayTypes;
  final String city;
  final String query;
  final SearchPoint? point;
  final double? radiusKm;
  final DateTime? startFrom;
  final DateTime? startTo;
  final bool womenFriendly;
  final bool verifiedHosts;
  final int? minStay;
  final GigSort sort;

  /// Query parameters for GET /api/v1/gigs/ (also the saved-search `params`).
  ///
  /// Leaves out anything the API would reject: a radius or distance sort
  /// without a point.
  Map<String, Object?> toParams() {
    String sorted(Iterable<String> values) =>
        (values.toList()..sort()).join(',');
    final p = point;
    final sortValue = sort == GigSort.distance && p == null
        ? GigSort.bestFit
        : sort;
    return {
      if (payModels.isNotEmpty)
        'compensation_model': sorted(payModels.map((m) => m.name)),
      if (roles.isNotEmpty) 'role': sorted(roles.map((r) => r.value)),
      if (stayTypes.isNotEmpty)
        'stay_type': sorted(stayTypes.map((s) => s.value)),
      if (city.trim().isNotEmpty) 'city': city.trim(),
      if (query.trim().isNotEmpty) 'q': query.trim(),
      if (p != null) ...{
        'latitude': p.latitude,
        'longitude': p.longitude,
        if (radiusKm != null) 'radius_km': radiusKm,
      },
      if (startFrom != null) 'start_from': formatDate(startFrom!),
      if (startTo != null) 'start_to': formatDate(startTo!),
      if (womenFriendly) 'women_friendly': true,
      if (verifiedHosts) 'verified_hosts': true,
      if (minStay != null) 'min_stay': minStay,
      'sort': sortValue.value,
    };
  }

  /// How many filters the sheet sets (the chips and search box aren't
  /// counted): shown as a badge on the filter button.
  int get sheetCount => [
    roles.isNotEmpty,
    stayTypes.isNotEmpty,
    city.trim().isNotEmpty,
    point != null,
    startFrom != null || startTo != null,
    verifiedHosts,
    minStay != null,
  ].where((set) => set).length;

  bool get isEmpty =>
      sheetCount == 0 &&
      payModels.isEmpty &&
      query.trim().isEmpty &&
      !womenFriendly;

  DiscoveryFilters copyWith({
    Set<PayModel>? payModels,
    Set<RoleTemplate>? roles,
    Set<StayType>? stayTypes,
    String? city,
    String? query,
    SearchPoint? Function()? point,
    double? Function()? radiusKm,
    DateTime? Function()? startFrom,
    DateTime? Function()? startTo,
    bool? womenFriendly,
    bool? verifiedHosts,
    int? Function()? minStay,
    GigSort? sort,
  }) => DiscoveryFilters(
    payModels: payModels ?? this.payModels,
    roles: roles ?? this.roles,
    stayTypes: stayTypes ?? this.stayTypes,
    city: city ?? this.city,
    query: query ?? this.query,
    point: point == null ? this.point : point(),
    radiusKm: radiusKm == null ? this.radiusKm : radiusKm(),
    startFrom: startFrom == null ? this.startFrom : startFrom(),
    startTo: startTo == null ? this.startTo : startTo(),
    womenFriendly: womenFriendly ?? this.womenFriendly,
    verifiedHosts: verifiedHosts ?? this.verifiedHosts,
    minStay: minStay == null ? this.minStay : minStay(),
    sort: sort ?? this.sort,
  );

  /// Keeps the chips and search, clears what the sheet sets.
  DiscoveryFilters clearSheet() => DiscoveryFilters(
    payModels: payModels,
    query: query,
    womenFriendly: womenFriendly,
    sort: sort == GigSort.distance ? GigSort.bestFit : sort,
  );

  @override
  bool operator ==(Object other) =>
      other is DiscoveryFilters && mapEquals(other.toParams(), toParams());

  @override
  int get hashCode => Object.hashAllUnordered(
    toParams().entries.map((e) => Object.hash(e.key, e.value)),
  );
}
