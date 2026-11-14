import 'package:flutter/foundation.dart';

/// Talent types, as the API lists them (backend apps/profiles/constants.py).
enum TalentType {
  artist('artist', 'Artist / muralist'),
  photoVideo('photo_video', 'Photographer / videographer'),
  contentCreator('content_creator', 'Content creator / social media'),
  musician('musician', 'Musician / performer'),
  wellness('wellness', 'Yoga / wellness'),
  culinary('culinary', 'Chef / barista'),
  hospitality('hospitality', 'Hospitality / front desk'),
  teacher('teacher', 'Teacher / workshop host'),
  tech('tech', 'Tech / design'),
  outdoor('outdoor', 'Outdoor / trek guide'),
  other('other', 'Other');

  new(this.value, this.label);

  final String value;
  final String label;

  static TalentType? parse(String? value) =>
      values.where((t) => t.value == value).firstOrNull;
}

/// Language codes the API accepts, with names (backend LANGUAGES).
const languageNames = <String, String>{
  'en': 'English',
  'hi': 'Hindi',
  'bn': 'Bengali',
  'mr': 'Marathi',
  'ta': 'Tamil',
  'te': 'Telugu',
  'kn': 'Kannada',
  'ml': 'Malayalam',
  'gu': 'Gujarati',
  'pa': 'Punjabi',
  'or': 'Odia',
  'as': 'Assamese',
  'kok': 'Konkani',
  'ne': 'Nepali',
  'ur': 'Urdu',
  'ar': 'Arabic',
  'de': 'German',
  'es': 'Spanish',
  'fr': 'French',
  'he': 'Hebrew',
  'it': 'Italian',
  'ja': 'Japanese',
  'ko': 'Korean',
  'nl': 'Dutch',
  'pt': 'Portuguese',
  'ru': 'Russian',
  'zh': 'Chinese',
};

@immutable
class Skill {
  const new({required this.slug, required this.name});

  factory fromJson(Map<String, Object?> json) =>
      Skill(slug: json['slug']! as String, name: json['name']! as String);

  final String slug;
  final String name;
}

/// The talent profile as GET/PATCH /api/v1/profiles/talent/me/ sends it.
@immutable
class TalentProfile {
  const new({
    this.displayName = '',
    this.bio = '',
    this.talentType,
    this.skills = const [],
    this.languages = const [],
    this.homeCity = '',
    this.emergencyContactName = '',
    this.emergencyContactPhone = '',
    this.dateOfBirth,
    this.instagramHandle = '',
    this.profileComplete = false,
    this.missingFields = const [],
  });

  factory fromJson(Map<String, Object?> json) {
    final dob = json['date_of_birth'] as String?;
    return TalentProfile(
      displayName: json['display_name'] as String? ?? '',
      bio: json['bio'] as String? ?? '',
      talentType: TalentType.parse(json['talent_type'] as String?),
      skills: [...?(json['skills'] as List?)?.cast<String>()],
      languages: [...?(json['languages'] as List?)?.cast<String>()],
      homeCity: json['home_city'] as String? ?? '',
      emergencyContactName: json['emergency_contact_name'] as String? ?? '',
      emergencyContactPhone: json['emergency_contact_phone'] as String? ?? '',
      dateOfBirth: dob == null || dob.isEmpty ? null : DateTime.parse(dob),
      instagramHandle: json['instagram_handle'] as String? ?? '',
      profileComplete: json['profile_complete'] as bool? ?? false,
      missingFields: [...?(json['missing_fields'] as List?)?.cast<String>()],
    );
  }

  final String displayName;
  final String bio;
  final TalentType? talentType;
  final List<String> skills;
  final List<String> languages;
  final String homeCity;
  final String emergencyContactName;
  final String emergencyContactPhone;

  /// A calendar date (no time zone), sent as YYYY-MM-DD.
  final DateTime? dateOfBirth;
  final String instagramHandle;
  final bool profileComplete;
  final List<String> missingFields;

  /// The PATCH body (read-only fields left out).
  Map<String, Object?> toJson() => {
    'display_name': displayName,
    'bio': bio,
    'talent_type': talentType?.value ?? '',
    'skills': skills,
    'languages': languages,
    'home_city': homeCity,
    'emergency_contact_name': emergencyContactName,
    'emergency_contact_phone': emergencyContactPhone,
    'date_of_birth': dateOfBirth == null ? null : formatDate(dateOfBirth!),
    'instagram_handle': instagramHandle,
  };
}

String formatDate(DateTime date) =>
    '${date.year.toString().padLeft(4, '0')}-'
    '${date.month.toString().padLeft(2, '0')}-'
    '${date.day.toString().padLeft(2, '0')}';
