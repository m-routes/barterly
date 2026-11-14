import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/profile/talent_profile.dart' show formatDate;
import 'package:flutter/foundation.dart';

/// The API allows this many attachments per application
/// (backend apps/applications/constants.py MAX_ATTACHMENTS).
const maxAttachments = 8;
const maxPitchLength = 2000;
const maxAnswerLength = 1000;

enum AttachmentKind {
  photo,
  video,
  document,
  link;

  static AttachmentKind parse(String? value) =>
      values.where((k) => k.name == value).firstOrNull ?? document;
}

/// An attachment in a draft: a file on the device (uploaded when the draft is
/// sent) or an https link.
@immutable
class AttachmentDraft {
  const new({
    required this.kind,
    this.localPath,
    this.contentType,
    this.sizeBytes,
    this.url,
    this.title = '',
    this.mediaId,
  });

  factory fromJson(Map<String, Object?> json) => AttachmentDraft(
    kind: AttachmentKind.parse(json['kind'] as String?),
    localPath: json['local_path'] as String?,
    contentType: json['content_type'] as String?,
    sizeBytes: (json['size_bytes'] as num?)?.toInt(),
    url: json['url'] as String?,
    title: json['title'] as String? ?? '',
    mediaId: json['media_id'] as String?,
  );

  final AttachmentKind kind;
  final String? localPath;
  final String? contentType;
  final int? sizeBytes;
  final String? url;
  final String title;

  /// Set once the file is uploaded and confirmed, so a retry doesn't upload
  /// it again.
  final String? mediaId;

  bool get isLink => kind == AttachmentKind.link;

  AttachmentDraft withMediaId(String id) => AttachmentDraft(
    kind: kind,
    localPath: localPath,
    contentType: contentType,
    sizeBytes: sizeBytes,
    url: url,
    title: title,
    mediaId: id,
  );

  Map<String, Object?> toJson() => {
    'kind': kind.name,
    'local_path': localPath,
    'content_type': contentType,
    'size_bytes': sizeBytes,
    'url': url,
    'title': title,
    'media_id': mediaId,
  };

  /// The API's attachment input. Uploads need [mediaId] set first.
  Map<String, Object?> toApi() => isLink
      ? {'kind': 'link', 'url': url, 'title': ?_title}
      : {'kind': kind.name, 'media_id': mediaId, 'title': ?_title};

  String? get _title => title.trim().isEmpty ? null : title.trim();
}

enum DraftStatus {
  /// Waiting for a network.
  queued,
  sending,

  /// The API said no (422 reasons or a validation error): needs the talent.
  needsAttention,
}

/// An application written on the device, kept until the API accepts it.
@immutable
class ApplicationDraft {
  const new({
    required this.localId,
    required this.gigId,
    required this.gigTitle,
    required this.pitch,
    required this.proposedStart,
    required this.proposedEnd,
    required this.createdAt,
    this.place = '',
    this.answers = const [],
    this.attachments = const [],
    this.status = DraftStatus.queued,
    this.problems = const [],
  });

  factory fromJson(Map<String, Object?> json) => ApplicationDraft(
    localId: json['local_id']! as String,
    gigId: json['gig_id']! as String,
    gigTitle: json['gig_title'] as String? ?? '',
    place: json['place'] as String? ?? '',
    pitch: json['pitch'] as String? ?? '',
    answers: [...?(json['answers'] as List?)?.whereType<String>()],
    proposedStart: DateTime.parse(json['proposed_start']! as String),
    proposedEnd: DateTime.parse(json['proposed_end']! as String),
    attachments: [
      for (final a in (json['attachments'] as List?) ?? const [])
        if (a is Map<String, Object?>) AttachmentDraft.fromJson(a),
    ],
    createdAt: DateTime.parse(json['created_at']! as String),
    // A draft that was mid-send when the app closed goes back in the queue.
    status: switch (json['status']) {
      'needsAttention' => DraftStatus.needsAttention,
      _ => DraftStatus.queued,
    },
    problems: [...?(json['problems'] as List?)?.whereType<String>()],
  );

  final String localId;
  final String gigId;
  final String gigTitle;
  final String place;
  final String pitch;
  final List<String> answers;
  final DateTime proposedStart;
  final DateTime proposedEnd;
  final List<AttachmentDraft> attachments;
  final DateTime createdAt;
  final DraftStatus status;

  /// Why the API refused it, in words to show the talent.
  final List<String> problems;

  ApplicationDraft copyWith({
    List<AttachmentDraft>? attachments,
    DraftStatus? status,
    List<String>? problems,
  }) => ApplicationDraft(
    localId: localId,
    gigId: gigId,
    gigTitle: gigTitle,
    place: place,
    pitch: pitch,
    answers: answers,
    proposedStart: proposedStart,
    proposedEnd: proposedEnd,
    attachments: attachments ?? this.attachments,
    createdAt: createdAt,
    status: status ?? this.status,
    problems: problems ?? this.problems,
  );

  Map<String, Object?> toJson() => {
    'local_id': localId,
    'gig_id': gigId,
    'gig_title': gigTitle,
    'place': place,
    'pitch': pitch,
    'answers': answers,
    'proposed_start': formatDate(proposedStart),
    'proposed_end': formatDate(proposedEnd),
    'attachments': [for (final a in attachments) a.toJson()],
    'created_at': createdAt.toUtc().toIso8601String(),
    'status': status.name,
    'problems': problems,
  };

  /// POST /api/v1/gigs/{id}/applications/ body. Every upload must have a
  /// media id by now.
  Map<String, Object?> toApi() => {
    'pitch': pitch.trim(),
    'answers': [for (final a in answers) a.trim()],
    'proposed_start': formatDate(proposedStart),
    'proposed_end': formatDate(proposedEnd),
    'attachments': [for (final a in attachments) a.toApi()],
  };
}

/// An application the API has, from GET /api/v1/applications/mine/.
@immutable
class Application {
  const new({
    required this.id,
    required this.gigId,
    required this.gigTitle,
    required this.status,
    this.proposedStart,
    this.proposedEnd,
    this.appliedAt,
    this.attachmentCount = 0,
    this.fitScore,
  });

  factory fromJson(Map<String, Object?> json) => Application(
    id: json['id']! as String,
    gigId: json['gig'] as String? ?? '',
    gigTitle: json['gig_title'] as String? ?? '',
    status: ApplicationStatus.parse(json['status'] as String?),
    proposedStart: DateTime.tryParse(json['proposed_start'] as String? ?? ''),
    proposedEnd: DateTime.tryParse(json['proposed_end'] as String? ?? ''),
    appliedAt: DateTime.tryParse(json['applied_at'] as String? ?? ''),
    attachmentCount:
        (json['attachment_count'] as num?)?.toInt() ??
        (json['attachments'] as List?)?.length ??
        0,
    fitScore: ((json['fit'] as Map?)?['score'] as num?)?.round(),
  );

  final String id;
  final String gigId;
  final String gigTitle;
  final ApplicationStatus status;
  final DateTime? proposedStart;
  final DateTime? proposedEnd;
  final DateTime? appliedAt;
  final int attachmentCount;
  final int? fitScore;
}

enum ApplicationStatus {
  applied('applied', 'Applied', active: true),
  shortlisted('shortlisted', 'Shortlisted', active: true),
  interview('interview', 'Interview', active: true),
  offered('offered', 'Offered', active: true),
  withdrawn('withdrawn', 'Withdrawn'),
  declined('declined', 'Declined'),
  rejected('rejected', 'Not selected'),
  expired('expired', 'Expired');

  new(this.value, this.label, {this.active = false});

  final String value;
  final String label;

  /// Still in play: the talent can withdraw.
  final bool active;

  static ApplicationStatus parse(String? value) =>
      values.where((s) => s.value == value).firstOrNull ?? applied;
}

/// One reason the API gave for refusing an application (422).
@immutable
class BlockedReason {
  const new(this.code, this.message);

  final String code;
  final String message;
}

/// The reasons in a 422 `application_blocked`, or empty for other errors.
List<BlockedReason> blockedReasons(ApiError error) {
  if (error.code != 'application_blocked') return const [];
  final reasons = error.details['reasons'];
  if (reasons is! List) return const [];
  return [
    for (final r in reasons)
      if (r is Map)
        BlockedReason(
          r['code'] as String? ?? '',
          r['message'] as String? ?? '',
        ),
  ];
}
