import 'package:barterly/src/agreements/terms.dart';
import 'package:flutter/foundation.dart';

List<String> _strings(Object? value) => [
  for (final v in (value as List?) ?? const []) '$v',
];

/// One revision of an offer (backend apps/offers/serializers.py).
@immutable
class Offer {
  const new({
    required this.id,
    required this.revision,
    required this.proposedBy,
    required this.mine,
    required this.terms,
    required this.status,
    this.changedFields = const [],
    this.isFinal = false,
    this.message = '',
  });

  factory fromJson(Map<String, Object?> json) => Offer(
    id: json['id']! as String,
    revision: (json['revision'] as num?)?.toInt() ?? 1,
    proposedBy: json['proposed_by'] as String? ?? 'vendor',
    mine: json['mine'] as bool? ?? false,
    terms: Terms.fromJson(json['terms']! as Map<String, Object?>),
    status: json['status'] as String? ?? 'open',
    changedFields: _strings(json['changed_fields']),
    isFinal: json['final'] as bool? ?? false,
    message: json['message'] as String? ?? '',
  );

  final String id;
  final int revision;
  final String proposedBy;
  final bool mine;
  final Terms terms;
  final String status;
  final List<String> changedFields;
  final bool isFinal;
  final String message;

  bool get isOpen => status == 'open';
}

@immutable
class OfferThread {
  const new({
    required this.offers,
    this.openOfferId,
    this.yourTurn = false,
    this.canCounter = false,
    this.counterable = const [],
    this.expiresAt,
  });

  factory fromJson(Map<String, Object?> json) => OfferThread(
    offers: [
      for (final o in (json['offers'] as List?) ?? const [])
        if (o is Map<String, Object?>) Offer.fromJson(o),
    ],
    openOfferId: json['open_offer'] as String?,
    yourTurn: json['your_turn'] as bool? ?? false,
    canCounter: json['can_counter'] as bool? ?? false,
    counterable: _strings(json['counterable']),
    expiresAt: DateTime.tryParse(json['offer_expires_at'] as String? ?? ''),
  );

  final List<Offer> offers;
  final String? openOfferId;
  final bool yourTurn;
  final bool canCounter;
  final List<String> counterable;
  final DateTime? expiresAt;

  /// The offer to show first: the open one, else the latest.
  Offer? get current =>
      offers.where((o) => o.id == openOfferId).firstOrNull ?? offers.lastOrNull;
}

/// One version of an agreement (backend apps/agreements/serializers.py).
@immutable
class AgreementVersion {
  const new({
    required this.id,
    required this.number,
    required this.status,
    required this.terms,
    this.changedFields = const [],
    this.changeReason = '',
    this.proposedBy = '',
    this.templateReviewed = false,
    this.pdfReady = false,
    this.pdfSha256 = '',
    this.signedBy = const {},
    this.signedByMe = false,
    this.canSign = false,
  });

  factory fromJson(Map<String, Object?> json) => AgreementVersion(
    id: json['id']! as String,
    number: (json['number'] as num?)?.toInt() ?? 1,
    status: json['status'] as String? ?? 'awaiting',
    terms: Terms.fromJson(json['terms']! as Map<String, Object?>),
    changedFields: _strings(json['changed_fields']),
    changeReason: json['change_reason'] as String? ?? '',
    proposedBy: json['proposed_by'] as String? ?? '',
    templateReviewed: json['template_reviewed'] as bool? ?? false,
    pdfReady: json['pdf_ready'] as bool? ?? false,
    pdfSha256: json['pdf_sha256'] as String? ?? '',
    signedBy: {
      for (final s in (json['signatures'] as List?) ?? const [])
        if (s is Map<String, Object?>)
          '${s['party']}':
              DateTime.tryParse(s['signed_at'] as String? ?? '') ??
              DateTime.now(),
    },
    signedByMe: json['signed_by_me'] as bool? ?? false,
    canSign: json['can_sign'] as bool? ?? false,
  );

  final String id;
  final int number;
  final String status;
  final Terms terms;
  final List<String> changedFields;
  final String changeReason;
  final String proposedBy;
  final bool templateReviewed;
  final bool pdfReady;
  final String pdfSha256;

  /// Side ("talent" / "vendor") → when they signed.
  final Map<String, DateTime> signedBy;
  final bool signedByMe;
  final bool canSign;

  String get statusLabel => switch (status) {
    'awaiting' => 'Waiting for signatures',
    'active' => 'In force',
    'superseded' => 'Replaced',
    'declined' => 'Change declined',
    'voided' => 'Replaced before signing',
    _ => status,
  };
}

@immutable
class Agreement {
  const new({
    required this.id,
    required this.bookingId,
    required this.gigTitle,
    required this.versions,
    this.bookingStatus = 'confirmed',
    this.inForce = false,
    this.currentVersion,
    this.mySide = 'talent',
  });

  factory fromJson(Map<String, Object?> json) => Agreement(
    id: json['id']! as String,
    bookingId: json['booking'] as String? ?? '',
    gigTitle: json['gig_title'] as String? ?? '',
    bookingStatus: json['booking_status'] as String? ?? 'confirmed',
    inForce: json['in_force'] as bool? ?? false,
    currentVersion: (json['current_version'] as num?)?.toInt(),
    mySide: json['my_side'] as String? ?? 'talent',
    versions: [
      for (final v in (json['versions'] as List?) ?? const [])
        if (v is Map<String, Object?>) AgreementVersion.fromJson(v),
    ],
  );

  final String id;
  final String bookingId;
  final String gigTitle;
  final String bookingStatus;
  final bool inForce;
  final int? currentVersion;
  final String mySide;

  /// Newest first.
  final List<AgreementVersion> versions;
}

/// What signing a version needs (GET .../sign/).
@immutable
class SignChallenge {
  const new({
    required this.method,
    required this.consentText,
    required this.documentSha256,
    this.phoneHint = '',
  });

  factory fromJson(Map<String, Object?> json) => SignChallenge(
    method: json['method'] as String? ?? 'otp',
    consentText: json['consent_text'] as String? ?? '',
    documentSha256: json['document_sha256'] as String? ?? '',
    phoneHint: json['phone_hint'] as String? ?? '',
  );

  final String method;
  final String consentText;
  final String documentSha256;
  final String phoneHint;

  bool get needsOtp => method == 'otp';
}
