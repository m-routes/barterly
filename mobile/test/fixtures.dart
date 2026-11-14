import 'package:barterly/src/profile/talent_profile.dart' show formatDate;

// API bodies for discover, gigs and applications tests, in the shapes the
// backend sends (apps/discovery/serializers.py, apps/applications/...).

DateTime _today() {
  final now = DateTime.now();
  return DateTime(now.year, now.month, now.day);
}

/// Fixture gigs start four weeks from today and run four weeks, so date
/// rules hold whenever the tests run.
final DateTime gigStart = _today().add(const Duration(days: 28));
final DateTime gigEnd = gigStart.add(const Duration(days: 28));

Map<String, Object?> gigJson({
  String id = 'g1',
  String title = 'Reception and social media volunteer',
  String model = 'volunteer',
  String property = 'Pine Trail Hostel',
  String city = 'Kasol',
  double? lat = 32.01,
  double? lng = 77.31,
  int fit = 92,
  String? startDate,
  String? endDate,
  int? minStay = 14,
  bool womenFriendly = true,
  bool hostVerified = true,
}) => {
  'id': id,
  'title': title,
  'role_template': 'volunteer',
  'compensation_model': model,
  'start_date': startDate ?? formatDate(gigStart),
  'end_date': endDate ?? formatDate(gigEnd),
  'duration_days': null,
  'apply_by': null,
  'slots': 2,
  'hours_per_day': 4,
  'days_per_week': 5,
  'stay_type': 'dorm_bed',
  'meals': 'all_meals',
  'wifi': true,
  'stipend_amount': model == 'hybrid' ? '6000.00' : null,
  'stipend_period': model == 'hybrid' ? 'per_month' : '',
  'deliverables': [
    {'type': 'instagram_story', 'quantity': 2, 'notes': 'tag the property'},
  ],
  'skills': ['photography'],
  'languages': ['en', 'hi'],
  'min_followers': 0,
  'min_stay_days': minStay,
  'required_verification': 'none',
  'published_at': '2026-11-01T10:00:00Z',
  'property': {
    'id': 'p-$id',
    'name': property,
    'property_type': 'hostel',
    'city': city,
    'state': 'Himachal Pradesh',
    'women_friendly': womenFriendly,
    'verified': true,
    'approximate_location': lat == null || lng == null
        ? null
        : {'latitude': lat, 'longitude': lng, 'radius_m': 1500},
    'cover_thumb_url': null,
  },
  'host_verified': hostVerified,
  'distance_km': null,
  'fit': {
    'score': fit,
    'breakdown': {
      'skills': {
        'value': 1.0,
        'weight': 0.3,
        'points': 30.0,
        'neutral': false,
        'reason': 'You have 1 of 1 skills.',
      },
      'reliability': {
        'value': 0.5,
        'weight': 0.25,
        'points': 12.5,
        'neutral': true,
        'reason': 'No past gigs yet.',
      },
    },
  },
};

Map<String, Object?> page(List<Map<String, Object?>> gigs, {String? next}) => {
  'results': gigs,
  'next_cursor': next,
  'next': null,
};

Map<String, Object?> applicationJson({
  String id = 'a1',
  String gig = 'g1',
  String status = 'applied',
  int attachments = 0,
}) => {
  'id': id,
  'gig': gig,
  'gig_title': 'Reception and social media volunteer',
  'status': status,
  'proposed_start': '2026-12-12',
  'proposed_end': '2026-12-26',
  'applicant': <String, Object?>{},
  'fit': {'score': 92, 'breakdown': <String, Object?>{}},
  'attachment_count': attachments,
  'applied_at': '2026-11-14T10:00:00Z',
};

Map<String, Object?> uploadTicket(String mediaId) => {
  'media_id': mediaId,
  'upload_url': 'https://storage.test/upload/$mediaId',
  'method': 'PUT',
  'headers': {'Content-Type': 'image/jpeg', 'x-goog-meta-owner': 'u1'},
  'expires_at': '2026-11-14T11:00:00Z',
};
