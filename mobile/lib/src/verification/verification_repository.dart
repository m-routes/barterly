import 'package:barterly/src/api/api_error.dart';
import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

/// Verification as GET /api/v1/verification/me/ sends it
/// (backend apps/verification/serializers.py).

enum CaseStatus {
  notStarted('not_started', 'Not started'),
  submitted('submitted', 'Submitted'),
  inReview('in_review', 'In review'),
  approved('approved', 'Verified'),
  rejected('rejected', 'Not approved'),
  changesRequested('changes_requested', 'Changes needed'),
  expired('expired', 'Expired');

  new(this.value, this.label);

  final String value;
  final String label;

  static CaseStatus parse(String? value) =>
      values.where((s) => s.value == value).firstOrNull ?? notStarted;

  bool get pending => this == submitted || this == inReview;

  /// The talent can start (or restart) the check.
  bool get canStart =>
      this == notStarted ||
      this == rejected ||
      this == changesRequested ||
      this == expired;
}

enum BadgeKind {
  idVerified('id_verified', 'ID verified'),
  propertyVerified('property_verified', 'Property verified'),
  licenceVerified('licence_verified', 'Licence verified'),
  socialVerified('social_verified', 'Social verified'),
  referenceChecked('reference_checked', 'Reference checked'),
  trustedMember('trusted_member', 'Trusted member');

  new(this.value, this.label);

  final String value;
  final String label;

  static BadgeKind? parse(String? value) =>
      values.where((b) => b.value == value).firstOrNull;
}

/// IDs the KYC provider accepts (backend ID_DOCUMENT_CHOICES).
enum IdDocument {
  aadhaar('aadhaar', 'Aadhaar'),
  passport('passport', 'Passport'),
  drivingLicence('driving_licence', 'Driving licence'),
  voterId('voter_id', 'Voter ID');

  new(this.value, this.label);

  final String value;
  final String label;
}

@immutable
class VerificationCase {
  const new({
    required this.id,
    required this.status,
    this.reason = '',
    this.details = const {},
  });

  factory fromJson(Map<String, Object?> json) => VerificationCase(
    id: json['id']! as String,
    status: CaseStatus.parse(json['status'] as String?),
    reason: json['reason'] as String? ?? '',
    details: (json['details'] as Map?)?.cast<String, Object?>() ?? const {},
  );

  final String id;
  final CaseStatus status;

  /// Why it was rejected or what to change, from the trust team.
  final String reason;
  final Map<String, Object?> details;
}

@immutable
class CheckSummary {
  const new({
    required this.checkType,
    required this.label,
    required this.required,
    required this.badge,
    this.cases = const [],
  });

  factory fromJson(Map<String, Object?> json) => CheckSummary(
    checkType: json['check_type'] as String? ?? '',
    label: json['label'] as String? ?? '',
    required: json['required'] as bool? ?? false,
    badge: BadgeKind.parse(json['badge'] as String?),
    cases: [
      for (final c in (json['cases'] as List?) ?? const [])
        if (c is Map<String, Object?>) VerificationCase.fromJson(c),
    ],
  );

  final String checkType;
  final String label;

  /// Needed for the trusted member badge.
  final bool required;
  final BadgeKind? badge;
  final List<VerificationCase> cases;

  /// The newest case, or null if never started.
  VerificationCase? get latest => cases.lastOrNull;
  CaseStatus get status => latest?.status ?? CaseStatus.notStarted;
}

@immutable
class MyVerification {
  const new({
    required this.checks,
    required this.badges,
    required this.trustedMember,
  });

  factory fromJson(Map<String, Object?> json) => MyVerification(
    checks: [
      for (final c in (json['checks'] as List?) ?? const [])
        if (c is Map<String, Object?>) CheckSummary.fromJson(c),
    ],
    badges: {
      for (final b in (json['badges'] as List?) ?? const [])
        if (b is Map) ?BadgeKind.parse(b['kind'] as String?),
    },
    trustedMember: json['trusted_member'] as bool? ?? false,
  );

  final List<CheckSummary> checks;
  final Set<BadgeKind> badges;
  final bool trustedMember;

  CheckSummary? check(String type) =>
      checks.where((c) => c.checkType == type).firstOrNull;
}

/// A started ID check: open [redirectUrl] (the provider's hosted ID and
/// selfie page) or hand [clientToken] to the provider's SDK.
@immutable
class KycSession {
  const new({
    required this.caseId,
    required this.redirectUrl,
    required this.clientToken,
    required this.expiresIn,
  });

  final String caseId;
  final Uri redirectUrl;
  final String clientToken;
  final Duration expiresIn;
}

class VerificationRepository {
  new(this._dio);

  final Dio _dio;

  static const idCheck = 'id_selfie';
  static const socialCheck = 'social_account';

  Future<MyVerification> me() => guardApi(() async {
    final response = await _dio.get<Map<String, Object?>>(
      '/api/v1/verification/me/',
    );
    return MyVerification.fromJson(response.data!);
  });

  Future<KycSession> startIdCheck(IdDocument document) => guardApi(() async {
    final response = await _dio.post<Map<String, Object?>>(
      '/api/v1/verification/checks/id/',
      data: {'document_type': document.value},
    );
    final body = response.data!;
    final session = (body['session']! as Map).cast<String, Object?>();
    final url = Uri.parse(session['redirect_url']! as String);
    if (url.scheme != 'https') {
      // Never open a non-https page for an ID check.
      throw const ApiError(
        status: 0,
        code: 'kyc_unavailable',
        message: "ID verification isn't available right now. Try again later.",
      );
    }
    return KycSession(
      caseId: (body['case']! as Map)['id']! as String,
      redirectUrl: url,
      clientToken: session['client_token'] as String? ?? '',
      expiresIn: Duration(
        seconds: (session['expires_in_seconds'] as num?)?.toInt() ?? 0,
      ),
    );
  });

  /// Submits the Instagram handle on the profile. The returned case's
  /// `details.bio_code` must be in the account's bio while it is checked.
  Future<VerificationCase> submitSocial() => guardApi(() async {
    final response = await _dio.post<Map<String, Object?>>(
      '/api/v1/verification/checks/social/',
    );
    return VerificationCase.fromJson(response.data!);
  });
}
