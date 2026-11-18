import 'package:barterly/src/apply/application.dart';
import 'package:flutter/foundation.dart';

/// One application in full (GET /api/v1/applications/{id}/): its status
/// history and the interview being arranged, if any.
@immutable
class ApplicationDetail {
  const new({
    required this.application,
    this.timeline = const [],
    this.interview,
    this.place = '',
  });

  factory fromJson(Map<String, Object?> json) => ApplicationDetail(
    application: Application.fromJson(json),
    timeline: [
      for (final t in (json['timeline'] as List?) ?? const [])
        if (t is Map<String, Object?>) TimelineEntry.fromJson(t),
    ],
    interview: switch (json['interview']) {
      final Map<String, Object?> i => Interview.fromJson(i),
      _ => null,
    },
  );

  final Application application;
  final List<TimelineEntry> timeline;
  final Interview? interview;
  final String place;
}

@immutable
class TimelineEntry {
  const new({required this.status, required this.at, this.reason = ''});

  factory fromJson(Map<String, Object?> json) => TimelineEntry(
    status: ApplicationStatus.parse(json['status'] as String?),
    at:
        DateTime.tryParse(json['at'] as String? ?? '') ??
        DateTime.fromMillisecondsSinceEpoch(0),
    reason: json['reason'] as String? ?? '',
  );

  final ApplicationStatus status;
  final DateTime at;
  final String reason;
}

enum InterviewStatus {
  proposed('proposed'),
  scheduled('scheduled'),
  newTimesRequested('new_times_requested'),
  cancelled('cancelled');

  new(this.value);

  final String value;

  static InterviewStatus parse(String? value) =>
      values.where((s) => s.value == value).firstOrNull ?? proposed;
}

@immutable
class InterviewSlot {
  const new({required this.id, required this.startsAt, this.label = ''});

  factory fromJson(Map<String, Object?> json) => InterviewSlot(
    id: (json['id'] as num?)?.toInt() ?? 0,
    startsAt:
        DateTime.tryParse(json['starts_at'] as String? ?? '') ??
        DateTime.fromMillisecondsSinceEpoch(0),
    label: json['starts_at_ist'] as String? ?? '',
  );

  final int id;
  final DateTime startsAt;

  /// The time as the API writes it in India time ("Fri 20 Nov, 4:00 pm").
  final String label;
}

@immutable
class Interview {
  const new({
    required this.id,
    required this.status,
    this.slots = const [],
    this.startsAt,
    this.startsAtLabel = '',
    this.durationMinutes = 30,
    this.videoLink = '',
    this.note = '',
  });

  factory fromJson(Map<String, Object?> json) => Interview(
    id: json['id']! as String,
    status: InterviewStatus.parse(json['status'] as String?),
    slots: [
      for (final s in (json['slots'] as List?) ?? const [])
        if (s is Map<String, Object?>) InterviewSlot.fromJson(s),
    ],
    startsAt: DateTime.tryParse(json['starts_at'] as String? ?? ''),
    startsAtLabel: json['starts_at_ist'] as String? ?? '',
    durationMinutes: (json['duration_minutes'] as num?)?.toInt() ?? 30,
    videoLink: json['video_link'] as String? ?? '',
    note: json['note'] as String? ?? '',
  );

  final String id;
  final InterviewStatus status;
  final List<InterviewSlot> slots;
  final DateTime? startsAt;
  final String startsAtLabel;
  final int durationMinutes;
  final String videoLink;
  final String note;

  bool get needsAPick => status == InterviewStatus.proposed && slots.isNotEmpty;
}

/// The trip's steps, as the canvas's segmented progress bar shows them.
enum TripStep {
  applied('Applied'),
  shortlisted('Shortlisted'),
  interview('Interview'),
  offer('Offer'),
  signed('Signed'),
  checkedIn('Checked in'),
  completed('Completed');

  new(this.label);

  final String label;
}

/// Where a trip is: how many steps are done, what comes next, and whether it
/// ended early (rejected, withdrawn, cancelled...). Pure, from the
/// application's status and the booking's (once there's an agreement).
@immutable
class TripProgress {
  const new({required this.done, required this.next, this.ended = ''});

  /// Steps completed: 1 (applied) to 7 (completed).
  final int done;
  final String next;

  /// Why the trip ended before completing, or empty.
  final String ended;

  bool get isOver => ended.isNotEmpty || done == TripStep.values.length;
}

TripProgress tripProgress(
  ApplicationStatus status, {
  String bookingStatus = '',
  Interview? interview,
}) {
  switch (status) {
    case ApplicationStatus.withdrawn:
      return const TripProgress(done: 1, next: '', ended: 'You withdrew');
    case ApplicationStatus.rejected:
      return const TripProgress(done: 1, next: '', ended: 'Not selected');
    case ApplicationStatus.declined:
      return const TripProgress(
        done: 4,
        next: '',
        ended: 'You declined the offer',
      );
    case ApplicationStatus.expired:
      return const TripProgress(done: 4, next: '', ended: 'The offer expired');
    case ApplicationStatus.applied:
      return const TripProgress(
        done: 1,
        next: 'The host is reviewing applications.',
      );
    case ApplicationStatus.shortlisted:
      return const TripProgress(
        done: 2,
        next: "You're shortlisted. The host may set up an interview.",
      );
    case ApplicationStatus.interview:
      final next = switch (interview?.status) {
        InterviewStatus.proposed => 'Pick a time for your interview.',
        InterviewStatus.scheduled =>
          'Interview on ${interview!.startsAtLabel}.',
        InterviewStatus.newTimesRequested =>
          'Waiting for the host to offer new times.',
        _ => 'The host will set up an interview.',
      };
      return TripProgress(done: 3, next: next);
    case ApplicationStatus.offered:
      return const TripProgress(done: 4, next: 'Review the offer and answer.');
    case ApplicationStatus.confirmed:
      return switch (bookingStatus) {
        'signing' || '' => const TripProgress(
          done: 4,
          next: 'Sign the agreement. The place is yours once you both sign.',
        ),
        'confirmed' => const TripProgress(
          done: 5,
          next: 'Check in at the property on your first day.',
        ),
        'checked_in' || 'delivering' => const TripProgress(
          done: 6,
          next: 'Enjoy your stay and keep up your side of the agreement.',
        ),
        'completed' || 'reviewed' => const TripProgress(done: 7, next: ''),
        'cancelled' => const TripProgress(
          done: 4,
          next: '',
          ended: 'The booking was cancelled',
        ),
        'no_show' => const TripProgress(
          done: 5,
          next: '',
          ended: 'Marked as a no-show',
        ),
        _ => const TripProgress(done: 5, next: ''),
      };
  }
}
