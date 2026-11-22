import 'package:flutter/foundation.dart';

/// One consent purpose, as GET /api/v1/privacy/consents/ sends it.
@immutable
class Consent {
  const new({
    required this.purpose,
    required this.label,
    required this.required,
    required this.granted,
    required this.version,
    required this.currentVersion,
    this.recordedAt,
  });

  factory fromJson(Map<String, Object?> json) => Consent(
    purpose: json['purpose']! as String,
    label: json['label']! as String,
    required: json['required']! as bool,
    granted: json['granted']! as bool,
    version: json['version'] as String? ?? '',
    currentVersion: json['current_version']! as String,
    recordedAt: switch (json['recorded_at']) {
      final String at => DateTime.parse(at),
      _ => null,
    },
  );

  final String purpose;
  final String label;

  /// Needed to use Barterly; withdrawn only by deleting the account.
  final bool required;
  final bool granted;
  final String version;
  final String currentVersion;
  final DateTime? recordedAt;
}

@immutable
class DataExport {
  const new({
    required this.id,
    required this.ready,
    required this.createdAt,
    required this.expiresAt,
  });

  factory fromJson(Map<String, Object?> json) => DataExport(
    id: json['id']! as String,
    ready: json['status'] == 'ready',
    createdAt: DateTime.parse(json['created_at']! as String),
    expiresAt: DateTime.parse(json['expires_at']! as String),
  );

  final String id;
  final bool ready;
  final DateTime createdAt;
  final DateTime expiresAt;
}

@immutable
class DeletionState {
  const new({
    required this.scheduledFor,
    required this.blockers,
    required this.graceDays,
  });

  factory fromJson(Map<String, Object?> json) {
    final request = json['request'] as Map<String, Object?>?;
    return DeletionState(
      scheduledFor: request == null
          ? null
          : DateTime.parse(request['scheduled_for']! as String),
      blockers: [
        for (final b in json['blockers']! as List<Object?>)
          (b! as Map<String, Object?>)['message']! as String,
      ],
      graceDays: json['grace_days']! as int,
    );
  }

  /// When the account will be anonymised, if deletion is scheduled.
  final DateTime? scheduledFor;

  /// What must be finished first (bookings, money in flight), in words.
  final List<String> blockers;
  final int graceDays;
}
