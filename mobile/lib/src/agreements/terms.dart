import 'package:flutter/foundation.dart';
import 'package:intl/intl.dart';

/// The terms of an offer or agreement version (backend apps/offers/terms.py).
/// Frozen on the server: the app only reads them and sends changes.
@immutable
class Terms {
  const new({
    required this.compensationModel,
    required this.startDate,
    required this.endDate,
    required this.hoursPerDay,
    required this.daysPerWeek,
    required this.stayType,
    required this.meals,
    required this.cancellationPolicy,
    this.stipendAmount,
    this.stipendPeriod = '',
    this.deliverables = const [],
    this.usageRights,
  });

  factory fromJson(Map<String, Object?> json) => Terms(
    compensationModel: json['compensation_model'] as String? ?? '',
    startDate: DateTime.parse(json['start_date']! as String),
    endDate: DateTime.parse(json['end_date']! as String),
    hoursPerDay: (json['hours_per_day'] as num?)?.toInt() ?? 0,
    daysPerWeek: (json['days_per_week'] as num?)?.toInt() ?? 0,
    stayType: json['stay_type'] as String? ?? '',
    meals: json['meals'] as String? ?? '',
    cancellationPolicy: json['cancellation_policy'] as String? ?? '',
    stipendAmount: json['stipend_amount'] as String?,
    stipendPeriod: json['stipend_period'] as String? ?? '',
    deliverables: [
      for (final d in (json['deliverables'] as List?) ?? const [])
        if (d is Map<String, Object?>) Deliverable.fromJson(d),
    ],
    usageRights: switch (json['usage_rights']) {
      final Map<String, Object?> u => UsageRights.fromJson(u),
      _ => null,
    },
  );

  final String compensationModel;
  final DateTime startDate;
  final DateTime endDate;
  final int hoursPerDay;
  final int daysPerWeek;
  final String stayType;
  final String meals;
  final String cancellationPolicy;
  final String? stipendAmount;
  final String stipendPeriod;
  final List<Deliverable> deliverables;
  final UsageRights? usageRights;

  int get weeklyHours => hoursPerDay * daysPerWeek;

  /// (field, label, value) rows in reading order.
  List<(String, String, String)> rows() => [
    ('start_date', 'Arrive', longDate(startDate)),
    ('end_date', 'Leave', longDate(endDate)),
    (
      'hours_per_day',
      'Hours',
      '$hoursPerDay a day, $daysPerWeek days a week '
          '(at most $weeklyHours a week)',
    ),
    ('stay_type', 'Stay', stayLabels[stayType] ?? stayType),
    ('meals', 'Meals', mealLabels[meals] ?? meals),
    if (stipendAmount != null)
      (
        'stipend_amount',
        'Stipend',
        '${inr(stipendAmount!)} ${periodLabels[stipendPeriod] ?? ''}'.trim(),
      ),
    if (deliverables.isNotEmpty)
      (
        'deliverables',
        'Deliverables',
        deliverables.map((d) => d.describe()).join(', '),
      ),
    if (usageRights case final u?)
      ('usage_rights', 'Content use', u.describe()),
    (
      'cancellation_policy',
      'Cancellation',
      cancellationLabels[cancellationPolicy] ?? cancellationPolicy,
    ),
  ];
}

@immutable
class Deliverable {
  const new({required this.type, required this.quantity, this.notes = ''});

  factory fromJson(Map<String, Object?> json) => Deliverable(
    type: json['type'] as String? ?? '',
    quantity: (json['quantity'] as num?)?.toInt() ?? 1,
    notes: json['notes'] as String? ?? '',
  );

  final String type;
  final int quantity;
  final String notes;

  Deliverable withQuantity(int value) =>
      Deliverable(type: type, quantity: value, notes: notes);

  Map<String, Object?> toJson() => {
    'type': type,
    'quantity': quantity,
    'notes': notes,
  };

  String get label => deliverableLabels[type] ?? type;

  String describe() => '$quantity × $label${notes.isEmpty ? '' : ' ($notes)'}';
}

@immutable
class UsageRights {
  const new({
    required this.scope,
    required this.durationMonths,
    required this.creditRequired,
  });

  factory fromJson(Map<String, Object?> json) => UsageRights(
    scope: json['scope'] as String? ?? '',
    durationMonths: (json['duration_months'] as num?)?.toInt() ?? 0,
    creditRequired: json['credit_required'] as bool? ?? false,
  );

  final String scope;
  final int durationMonths;
  final bool creditRequired;

  Map<String, Object?> toJson() => {
    'scope': scope,
    'duration_months': durationMonths,
    'credit_required': creditRequired,
  };

  String describe() =>
      '${usageLabels[scope] ?? scope}, for $durationMonths months'
      '${creditRequired ? ', with credit' : ''}';
}

String longDate(DateTime date) => DateFormat('EEE d MMM y').format(date);

String apiDate(DateTime date) => DateFormat('yyyy-MM-dd').format(date);

String inr(String amount) {
  final value = double.tryParse(amount);
  if (value == null) return amount;
  return NumberFormat.currency(
    locale: 'en_IN',
    symbol: '₹',
    decimalDigits: value == value.roundToDouble() ? 0 : 2,
  ).format(value);
}

/// Labels for the API's codes (backend apps/gigs/constants.py, apps/offers/terms.py).
const stayLabels = {
  'none': 'No stay',
  'dorm_bed': 'Dorm bed',
  'shared_room': 'Shared room',
  'private_room': 'Private room',
  'tent': 'Tent / camping',
};
const mealLabels = {
  'none': 'No meals',
  'breakfast': 'Breakfast',
  'two_meals': 'Two meals a day',
  'all_meals': 'All meals',
};
const periodLabels = {
  'total': 'for the whole stay',
  'per_week': 'per week',
  'per_month': 'per month',
};
const deliverableLabels = {
  'instagram_post': 'Instagram post',
  'instagram_reel': 'Instagram reel',
  'instagram_story': 'Instagram story',
  'youtube_video': 'YouTube video',
  'blog_post': 'Blog post',
  'photo_set': 'Edited photo set',
  'mural': 'Mural / artwork',
  'google_review': 'Google review',
  'other': 'Other',
};
const usageLabels = {
  'organic': "The host's own social channels and website",
  'organic_and_ads': 'Own channels, website and paid ads',
};
const cancellationLabels = {
  'flexible': 'Flexible: free to cancel up to 3 days before',
  'moderate': 'Moderate: free to cancel up to 7 days before',
  'strict': 'Strict: free to cancel up to 14 days before',
};

/// Whether a row stands for one of the [changed] fields (a change to
/// days_per_week shows in the hours row).
bool rowChanged(String field, List<String> changed) => switch (field) {
  'hours_per_day' =>
    changed.contains(field) || changed.contains('days_per_week'),
  'stipend_amount' =>
    changed.contains(field) || changed.contains('stipend_period'),
  _ => changed.contains(field),
};
