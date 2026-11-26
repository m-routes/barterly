/// Deliverables for barter and hybrid stays (backend apps/deliverables).
library;

enum DeliverableStatus {
  pending('To do'),
  submitted('Waiting for your host'),
  changesRequested('Changes asked for'),
  approved('Approved');

  new(this.label);
  final String label;

  static DeliverableStatus of(String value) => switch (value) {
    'submitted' => submitted,
    'changes_requested' => changesRequested,
    'approved' => approved,
    _ => pending,
  };
}

class SubmissionInfo {
  const new({
    required this.version,
    required this.postUrl,
    required this.files,
    required this.review,
    required this.reviewNote,
  });

  factory fromJson(Map<String, Object?> json) => SubmissionInfo(
    version: (json['version'] as num?)?.toInt() ?? 1,
    postUrl: json['post_url'] as String? ?? '',
    files: ((json['files'] as List?) ?? const []).length,
    review: json['review'] as String? ?? '',
    reviewNote: json['review_note'] as String? ?? '',
  );

  final int version;
  final String postUrl;
  final int files;
  final String review;
  final String reviewNote;
}

class StatsSnapshot {
  const new({
    required this.selfReported,
    required this.source,
    this.views,
    this.likes,
    this.comments,
  });

  factory fromJson(Map<String, Object?> json) => StatsSnapshot(
    selfReported: json['self_reported'] as bool? ?? false,
    source: json['source'] as String? ?? '',
    views: (json['views'] as num?)?.toInt(),
    likes: (json['likes'] as num?)?.toInt(),
    comments: (json['comments'] as num?)?.toInt(),
  );

  final bool selfReported;
  final String source;
  final int? views;
  final int? likes;
  final int? comments;
}

class Deliverable {
  const new({
    required this.id,
    required this.title,
    required this.notes,
    required this.dueDate,
    required this.status,
    required this.changeRoundsLeft,
    required this.disclosureRequired,
    required this.platform,
    required this.latest,
    required this.stats,
  });

  factory fromJson(Map<String, Object?> json) => Deliverable(
    id: json['id']! as String,
    title: json['title'] as String? ?? '',
    notes: json['notes'] as String? ?? '',
    dueDate: DateTime.parse(json['due_date']! as String),
    status: DeliverableStatus.of(json['status'] as String? ?? ''),
    changeRoundsLeft: (json['change_rounds_left'] as num?)?.toInt() ?? 0,
    disclosureRequired: json['disclosure_required'] as bool? ?? false,
    platform: json['platform'] as String? ?? 'other',
    latest: switch (json['latest_submission']) {
      final Map<String, Object?> s => SubmissionInfo.fromJson(s),
      _ => null,
    },
    stats: [
      for (final s in (json['stats'] as List?) ?? const [])
        if (s is Map<String, Object?>) StatsSnapshot.fromJson(s),
    ],
  );

  final String id;
  final String title;
  final String notes;
  final DateTime dueDate;
  final DeliverableStatus status;
  final int changeRoundsLeft;
  final bool disclosureRequired;
  final String platform;
  final SubmissionInfo? latest;
  final List<StatsSnapshot> stats;

  bool get canSubmit => status != DeliverableStatus.approved;
  bool get canReportStats =>
      status == DeliverableStatus.submitted ||
      status == DeliverableStatus.approved;
}
