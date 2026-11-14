import 'package:barterly/src/pay_model.dart';
import 'package:flutter/foundation.dart';
import 'package:intl/intl.dart';

/// Gigs as GET /api/v1/gigs/ sends them to talent
/// (backend apps/discovery/serializers.py GigCardSerializer).

PayModel? parsePayModel(String? value) =>
    PayModel.values.where((m) => m.name == value).firstOrNull;

enum StayType {
  none('none', 'No stay'),
  dormBed('dorm_bed', 'Dorm bed'),
  sharedRoom('shared_room', 'Shared room'),
  privateRoom('private_room', 'Private room'),
  tent('tent', 'Tent / camping');

  new(this.value, this.label);

  final String value;
  final String label;

  static StayType? parse(String? value) =>
      values.where((t) => t.value == value).firstOrNull;
}

enum RoleTemplate {
  volunteer('volunteer', 'Volunteer'),
  contentCreator('content_creator', 'Content creator'),
  tripLeader('trip_leader', 'Trip leader'),
  specialist('specialist', 'Specialist');

  new(this.value, this.label);

  final String value;
  final String label;

  static RoleTemplate? parse(String? value) =>
      values.where((t) => t.value == value).firstOrNull;
}

const _mealLabels = {
  'none': 'no meals',
  'breakfast': 'breakfast',
  'two_meals': '2 meals a day',
  'all_meals': 'all meals',
};

const _verificationLabels = {
  'id_verified': 'Needs a verified ID',
  'trusted_member': 'Trusted members only',
};

/// The approximate point the API shares before booking: a rounded location
/// and the radius it could be anywhere in. Never the exact address.
@immutable
class ApproxLocation {
  const new({
    required this.latitude,
    required this.longitude,
    required this.radiusM,
  });

  static ApproxLocation? fromJson(Object? json) {
    if (json is! Map) return null;
    final lat = json['latitude'];
    final lng = json['longitude'];
    if (lat is! num || lng is! num) return null;
    return ApproxLocation(
      latitude: lat.toDouble(),
      longitude: lng.toDouble(),
      radiusM: (json['radius_m'] as num?)?.toDouble() ?? 0,
    );
  }

  final double latitude;
  final double longitude;
  final double radiusM;

  Map<String, Object?> toJson() => {
    'latitude': latitude,
    'longitude': longitude,
    'radius_m': radiusM,
  };
}

@immutable
class GigProperty {
  const new({
    required this.id,
    required this.name,
    required this.propertyType,
    required this.city,
    required this.state,
    required this.womenFriendly,
    required this.verified,
    this.location,
    this.coverThumbUrl,
  });

  factory fromJson(Map<String, Object?> json) => GigProperty(
    id: json['id']! as String,
    name: json['name'] as String? ?? '',
    propertyType: json['property_type'] as String? ?? '',
    city: json['city'] as String? ?? '',
    state: json['state'] as String? ?? '',
    womenFriendly: json['women_friendly'] as bool? ?? false,
    verified: json['verified'] as bool? ?? false,
    location: ApproxLocation.fromJson(json['approximate_location']),
    coverThumbUrl: json['cover_thumb_url'] as String?,
  );

  final String id;
  final String name;
  final String propertyType;
  final String city;
  final String state;
  final bool womenFriendly;
  final bool verified;
  final ApproxLocation? location;
  final String? coverThumbUrl;

  String get place => [name, city].where((s) => s.isNotEmpty).join(' · ');
}

@immutable
class FitComponent {
  const new({
    required this.key,
    required this.value,
    required this.weight,
    required this.points,
    required this.neutral,
    required this.reason,
  });

  final String key;
  final double value;
  final double weight;
  final double points;

  /// No data yet: the API used a neutral value.
  final bool neutral;
  final String reason;
}

@immutable
class Fit {
  const new({required this.score, this.breakdown = const []});

  factory fromJson(Object? json) {
    if (json is! Map) return const Fit(score: 0);
    final breakdown = json['breakdown'];
    return Fit(
      score: (json['score'] as num?)?.round() ?? 0,
      breakdown: [
        if (breakdown is Map)
          for (final MapEntry(:key, :value) in breakdown.entries)
            if (value is Map)
              FitComponent(
                key: key as String,
                value: (value['value'] as num?)?.toDouble() ?? 0,
                weight: (value['weight'] as num?)?.toDouble() ?? 0,
                points: (value['points'] as num?)?.toDouble() ?? 0,
                neutral: value['neutral'] as bool? ?? false,
                reason: value['reason'] as String? ?? '',
              ),
      ],
    );
  }

  final int score;
  final List<FitComponent> breakdown;
}

@immutable
class Deliverable {
  const new({required this.type, required this.quantity, this.notes = ''});

  final String type;
  final int quantity;
  final String notes;

  String get label {
    final name = type.replaceAll('_', ' ');
    return notes.isEmpty ? '$quantity × $name' : '$quantity × $name: $notes';
  }
}

/// One gig. The discover list fills the card fields; [description] and
/// [screeningQuestions] come from the gig detail, when the API shares it.
@immutable
class Gig {
  const new({
    required this.id,
    required this.title,
    required this.property,
    this.json = const {},
    this.roleTemplate,
    this.payModel,
    this.startDate,
    this.endDate,
    this.durationDays,
    this.applyBy,
    this.slots = 1,
    this.hoursPerDay,
    this.daysPerWeek,
    this.stayType,
    this.meals = '',
    this.wifi = false,
    this.stipendAmount,
    this.stipendPeriod = '',
    this.deliverables = const [],
    this.skills = const [],
    this.languages = const [],
    this.minFollowers = 0,
    this.minStayDays,
    this.requiredVerification = 'none',
    this.hostVerified = false,
    this.distanceKm,
    this.fit = const Fit(score: 0),
    this.description,
    this.screeningQuestions,
  });

  factory fromJson(Map<String, Object?> json) {
    final property = json['property'];
    return Gig(
      json: json,
      id: json['id']! as String,
      title: json['title'] as String? ?? '',
      property: property is Map<String, Object?>
          ? GigProperty.fromJson(property)
          : const GigProperty(
              id: '',
              name: '',
              propertyType: '',
              city: '',
              state: '',
              womenFriendly: false,
              verified: false,
            ),
      roleTemplate: RoleTemplate.parse(json['role_template'] as String?),
      payModel: parsePayModel(json['compensation_model'] as String?),
      startDate: _date(json['start_date']),
      endDate: _date(json['end_date']),
      durationDays: (json['duration_days'] as num?)?.toInt(),
      applyBy: _date(json['apply_by']),
      slots: (json['slots'] as num?)?.toInt() ?? 1,
      hoursPerDay: (json['hours_per_day'] as num?)?.toInt(),
      daysPerWeek: (json['days_per_week'] as num?)?.toInt(),
      stayType: StayType.parse(json['stay_type'] as String?),
      meals: json['meals'] as String? ?? '',
      wifi: json['wifi'] as bool? ?? false,
      stipendAmount: _number(json['stipend_amount']),
      stipendPeriod: json['stipend_period'] as String? ?? '',
      deliverables: [
        for (final d in (json['deliverables'] as List?) ?? const [])
          if (d is Map)
            Deliverable(
              type: d['type'] as String? ?? 'other',
              quantity: (d['quantity'] as num?)?.toInt() ?? 1,
              notes: d['notes'] as String? ?? '',
            ),
      ],
      skills: [...?(json['skills'] as List?)?.whereType<String>()],
      languages: [...?(json['languages'] as List?)?.whereType<String>()],
      minFollowers: (json['min_followers'] as num?)?.toInt() ?? 0,
      minStayDays: (json['min_stay_days'] as num?)?.toInt(),
      requiredVerification: json['required_verification'] as String? ?? 'none',
      hostVerified: json['host_verified'] as bool? ?? false,
      distanceKm: (json['distance_km'] as num?)?.toDouble(),
      fit: Fit.fromJson(json['fit']),
      description: json['description'] as String?,
      screeningQuestions: (json['screening_questions'] as List?)
          ?.whereType<String>()
          .toList(),
    );
  }

  /// The JSON this came from, so the offline cache stores exactly what the
  /// API sent.
  final Map<String, Object?> json;

  final String id;
  final String title;
  final GigProperty property;
  final RoleTemplate? roleTemplate;
  final PayModel? payModel;
  final DateTime? startDate;
  final DateTime? endDate;
  final int? durationDays;
  final DateTime? applyBy;
  final int slots;
  final int? hoursPerDay;
  final int? daysPerWeek;
  final StayType? stayType;
  final String meals;
  final bool wifi;
  final double? stipendAmount;
  final String stipendPeriod;
  final List<Deliverable> deliverables;
  final List<String> skills;
  final List<String> languages;
  final int minFollowers;
  final int? minStayDays;
  final String requiredVerification;
  final bool hostVerified;
  final double? distanceKm;
  final Fit fit;
  final String? description;

  /// Null when unknown (the detail couldn't be loaded); empty when the gig
  /// has none.
  final List<String>? screeningQuestions;

  /// The detail's fields layered over the card's (the card has the fit score
  /// and distance, which the detail doesn't).
  Gig mergeDetail(Map<String, Object?> detail) => Gig.fromJson({
    ...json,
    ...detail,
    for (final key in _cardOnly) key: json[key],
  });

  /// Fields only the discover card has (the detail sends the property as an
  /// id and no score).
  static const _cardOnly = ['property', 'fit', 'distance_km', 'host_verified'];

  DateTime? get lastDay {
    if (endDate != null) return endDate;
    if (startDate != null && durationDays != null) {
      return startDate!.add(Duration(days: durationDays!));
    }
    return null;
  }

  /// "4 hrs/day · 5 days/week"
  String? get workSummary {
    final parts = [
      if (hoursPerDay != null) '$hoursPerDay hrs/day',
      if (daysPerWeek != null) '$daysPerWeek days/week',
    ];
    return parts.isEmpty ? null : parts.join(' · ');
  }

  /// "Dorm bed + all meals + ₹6,000/month"
  String get youGet {
    final parts = <String>[
      if (stayType != null && stayType != StayType.none) stayType!.label,
      if (meals.isNotEmpty && meals != 'none') _mealLabels[meals] ?? meals,
      if (stipendAmount != null) stipendLabel,
    ];
    return parts.isEmpty ? 'See details' : parts.join(' + ');
  }

  String get stipendLabel {
    final amount = formatRupees(stipendAmount ?? 0);
    return switch (stipendPeriod) {
      'per_week' => '$amount/week',
      'per_month' => '$amount/month',
      _ => '$amount stipend',
    };
  }

  /// "From 12 Dec · 2 slots"
  String get whenSummary {
    final parts = <String>[
      if (startDate != null) 'From ${shortDate(startDate!)}',
      '$slots ${slots == 1 ? 'slot' : 'slots'}',
      if (distanceKm != null) '${distanceKm!.toStringAsFixed(0)} km away',
    ];
    return parts.join(' · ');
  }

  String get stayLength {
    final start = startDate;
    final min = minStayDays;
    if (start == null && min == null) return 'Flexible';
    final from = start == null ? '' : ' from ${shortDate(start)}';
    if (min == null) return 'Starts${from.isEmpty ? ' anytime' : from}';
    return 'At least $min days$from';
  }

  String? get verificationNeeded => _verificationLabels[requiredVerification];
}

DateTime? _date(Object? value) =>
    value is String && value.isNotEmpty ? DateTime.tryParse(value) : null;

double? _number(Object? value) => switch (value) {
  final num n => n.toDouble(),
  final String s => double.tryParse(s),
  _ => null,
};

String shortDate(DateTime date) => DateFormat('d MMM').format(date);

/// "12 Dec to 9 Jan"
String dateRange(DateTime start, DateTime end) =>
    '${shortDate(start)} to ${shortDate(end)}';

String formatRupees(double amount) => NumberFormat.currency(
  locale: 'en_IN',
  symbol: '₹',
  decimalDigits: 0,
).format(amount);

/// One page of results and the cursor for the next.
@immutable
class GigPage {
  const new({required this.gigs, this.nextCursor});

  factory fromJson(Map<String, Object?> json) => GigPage(
    gigs: [
      for (final item in (json['results'] as List?) ?? const [])
        if (item is Map<String, Object?>) Gig.fromJson(item),
    ],
    nextCursor: json['next_cursor'] as String?,
  );

  final List<Gig> gigs;
  final String? nextCursor;

  Map<String, Object?> toJson() => {
    'results': [for (final g in gigs) g.json],
    'next_cursor': nextCursor,
  };
}
