/// Check-in passes and hour logs (backend apps/attendance).
library;

/// What the talent shows at arrival: [token] as a QR code, or the six-digit
/// code from [codeSecret]. Kept on the device so it works without signal.
class CheckInPass {
  const new({
    required this.bookingId,
    required this.token,
    required this.codeSecret,
    required this.codePeriodSeconds,
    required this.validFrom,
    required this.validUntil,
  });

  factory fromJson(Map<String, Object?> json) => CheckInPass(
    bookingId: json['booking_id']! as String,
    token: json['token']! as String,
    codeSecret: json['code_secret']! as String,
    codePeriodSeconds: (json['code_period_seconds'] as num?)?.toInt() ?? 300,
    validFrom: DateTime.parse(json['valid_from']! as String),
    validUntil: DateTime.parse(json['valid_until']! as String),
  );

  final String bookingId;
  final String token;
  final String codeSecret;
  final int codePeriodSeconds;
  final DateTime validFrom;
  final DateTime validUntil;

  bool validAt(DateTime moment) =>
      !moment.isBefore(validFrom) && moment.isBefore(validUntil);

  /// Worth asking for a fresh one (expired, or under two hours left).
  bool staleAt(DateTime moment) =>
      validUntil.difference(moment) < const Duration(hours: 2);

  Map<String, Object?> toJson() => {
    'booking_id': bookingId,
    'token': token,
    'code_secret': codeSecret,
    'code_period_seconds': codePeriodSeconds,
    'valid_from': validFrom.toIso8601String(),
    'valid_until': validUntil.toIso8601String(),
  };
}

enum HourStatus {
  pending('Waiting for your host'),
  confirmed('Confirmed'),
  disputed('Disputed');

  new(this.label);
  final String label;

  static HourStatus of(String value) => HourStatus.values.firstWhere(
    (s) => s.name == value,
    orElse: () => HourStatus.pending,
  );
}

class HourLog {
  const new({
    required this.id,
    required this.day,
    required this.minutes,
    required this.note,
    required this.status,
    required this.vendorNote,
  });

  factory fromJson(Map<String, Object?> json) => HourLog(
    id: json['id']! as String,
    day: DateTime.parse(json['day']! as String),
    minutes: (json['minutes']! as num).toInt(),
    note: json['note'] as String? ?? '',
    status: HourStatus.of(json['status'] as String? ?? ''),
    vendorNote: json['vendor_note'] as String? ?? '',
  );

  final String id;
  final DateTime day;
  final int minutes;
  final String note;
  final HourStatus status;
  final String vendorNote;
}

class HoursWeek {
  const new({
    required this.weekStart,
    required this.weekEnd,
    required this.logs,
    required this.minutes,
    required this.daysWorked,
    required this.weeklyCapMinutes,
    required this.hoursPerDay,
    required this.daysPerWeek,
  });

  factory fromJson(Map<String, Object?> json) => HoursWeek(
    weekStart: DateTime.parse(json['week_start']! as String),
    weekEnd: DateTime.parse(json['week_end']! as String),
    logs: [
      for (final l in (json['logs'] as List?) ?? const [])
        if (l is Map<String, Object?>) HourLog.fromJson(l),
    ],
    minutes: (json['minutes'] as num?)?.toInt() ?? 0,
    daysWorked: (json['days_worked'] as num?)?.toInt() ?? 0,
    weeklyCapMinutes: (json['weekly_cap_minutes'] as num?)?.toInt() ?? 0,
    hoursPerDay: (json['hours_per_day'] as num?)?.toInt() ?? 0,
    daysPerWeek: (json['days_per_week'] as num?)?.toInt() ?? 0,
  );

  final DateTime weekStart;
  final DateTime weekEnd;
  final List<HourLog> logs;
  final int minutes;
  final int daysWorked;
  final int weeklyCapMinutes;
  final int hoursPerDay;
  final int daysPerWeek;

  HourLog? logOn(DateTime day) {
    for (final log in logs) {
      if (log.day.year == day.year &&
          log.day.month == day.month &&
          log.day.day == day.day) {
        return log;
      }
    }
    return null;
  }
}

/// Whether a log would be allowed, why not, and what to watch out for.
class HoursCheck {
  const new({
    required this.allowed,
    required this.problems,
    required this.warnings,
  });

  factory fromJson(Map<String, Object?> json) => HoursCheck(
    allowed: json['allowed'] as bool? ?? false,
    problems: [for (final p in (json['problems'] as List?) ?? const []) '$p'],
    warnings: [for (final w in (json['warnings'] as List?) ?? const []) '$w'],
  );

  final bool allowed;
  final List<String> problems;
  final List<String> warnings;
}

String hoursLabel(int minutes) {
  final h = minutes ~/ 60;
  final m = minutes % 60;
  return m == 0 ? '$h h' : '$h h $m min';
}
