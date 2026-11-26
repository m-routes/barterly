import 'dart:async';

import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/attendance/attendance_models.dart';
import 'package:barterly/src/providers.dart';
import 'package:barterly/src/theme/tokens.dart';
import 'package:barterly/src/widgets/feedback.dart';
import 'package:barterly/src/widgets/states.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import 'package:material_ui/material_ui.dart';

/// The volunteer hour log: one week at a time, each day's hours and whether the
/// host confirmed them. Logging checks the agreement's weekly cap and day off
/// first, and says when you're getting close.
class HoursScreen extends ConsumerStatefulWidget {
  const new({required this.bookingId, super.key});

  final String bookingId;

  @override
  ConsumerState<HoursScreen> createState() => _HoursScreenState();
}

class _HoursScreenState extends ConsumerState<HoursScreen> {
  late DateTime _week = ref.read(clockProvider)();
  Future<HoursWeek>? _data;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  void _reload() {
    setState(() {
      _data = ref
          .read(attendanceRepositoryProvider)
          .week(widget.bookingId, _week);
    });
  }

  void _move(int days) {
    _week = _week.add(Duration(days: days));
    _reload();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Hours')),
    body: FutureBuilder<HoursWeek>(
      future: _data,
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          final e = snapshot.error;
          return ErrorView(
            title: "We couldn't load your hours",
            message: e is ApiError ? e.userMessage : '$e',
            onRetry: _reload,
          );
        }
        final week = snapshot.data;
        if (week == null) return const LoadingView(label: 'Loading hours…');
        return _WeekView(
          week: week,
          today: ref.read(clockProvider)(),
          onPrevious: () => _move(-7),
          onNext: () => _move(7),
          onLog: (day) async {
            final saved = await showModalBottomSheet<bool>(
              context: context,
              isScrollControlled: true,
              builder: (_) => _LogSheet(
                bookingId: widget.bookingId,
                day: day,
                existing: week.logOn(day),
              ),
            );
            if (saved ?? false) _reload();
          },
        );
      },
    ),
  );
}

class _WeekView extends StatelessWidget {
  const new({
    required this.week,
    required this.today,
    required this.onPrevious,
    required this.onNext,
    required this.onLog,
  });

  final HoursWeek week;
  final DateTime today;
  final VoidCallback onPrevious;
  final VoidCallback onNext;
  final void Function(DateTime day) onLog;

  @override
  Widget build(BuildContext context) {
    final range =
        '${DateFormat('d MMM').format(week.weekStart)} – '
        '${DateFormat('d MMM').format(week.weekEnd)}';
    final todayDate = DateTime(today.year, today.month, today.day);
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
      children: [
        Row(
          children: [
            IconButton(
              tooltip: 'Previous week',
              onPressed: onPrevious,
              icon: const Icon(Icons.chevron_left),
            ),
            Expanded(
              child: Text(
                range,
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.titleMedium,
              ),
            ),
            IconButton(
              tooltip: 'Next week',
              onPressed: onNext,
              icon: const Icon(Icons.chevron_right),
            ),
          ],
        ),
        SurfaceCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            spacing: BarterlySpace.xs,
            children: [
              Text(
                '${hoursLabel(week.minutes)} of '
                '${hoursLabel(week.weeklyCapMinutes)} this week',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              LinearProgressIndicator(
                value: week.weeklyCapMinutes == 0
                    ? 0
                    : (week.minutes / week.weeklyCapMinutes).clamp(0, 1),
                semanticsLabel: 'Hours this week',
              ),
              Text(
                '${week.daysWorked} of ${week.daysPerWeek} working days · '
                'up to ${week.hoursPerDay} h a day',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ),
        ),
        const SizedBox(height: BarterlySpace.md),
        for (var i = 0; i < 7; i++)
          _DayTile(
            day: week.weekStart.add(Duration(days: i)),
            log: week.logOn(week.weekStart.add(Duration(days: i))),
            canLog: !week.weekStart.add(Duration(days: i)).isAfter(todayDate),
            onTap: () => onLog(week.weekStart.add(Duration(days: i))),
          ),
      ],
    );
  }
}

class _DayTile extends StatelessWidget {
  const new({
    required this.day,
    required this.log,
    required this.canLog,
    required this.onTap,
  });

  final DateTime day;
  final HourLog? log;
  final bool canLog;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final entry = log;
    final locked = entry?.status == HourStatus.confirmed;
    return ListTile(
      contentPadding: EdgeInsets.zero,
      title: Text(DateFormat('EEE d MMM').format(day)),
      subtitle: entry == null
          ? null
          : Text(
              [
                entry.status.label,
                if (entry.vendorNote.isNotEmpty) entry.vendorNote,
              ].join(' · '),
            ),
      trailing: entry != null
          ? Text(hoursLabel(entry.minutes))
          : canLog
          ? const Text('Log')
          : null,
      enabled: canLog && !locked,
      onTap: canLog && !locked ? onTap : null,
    );
  }
}

class _LogSheet extends ConsumerStatefulWidget {
  const new({required this.bookingId, required this.day, this.existing});

  final String bookingId;
  final DateTime day;
  final HourLog? existing;

  @override
  ConsumerState<_LogSheet> createState() => _LogSheetState();
}

class _LogSheetState extends ConsumerState<_LogSheet> {
  late int _minutes = widget.existing?.minutes ?? 120;
  late final _note = TextEditingController(text: widget.existing?.note ?? '');
  HoursCheck? _check;
  String? _error;
  bool _saving = false;
  Timer? _debounce;

  @override
  void initState() {
    super.initState();
    _preview();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _note.dispose();
    super.dispose();
  }

  void _preview() {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 250), () async {
      try {
        final check = await ref
            .read(attendanceRepositoryProvider)
            .check(widget.bookingId, day: widget.day, minutes: _minutes);
        if (mounted) setState(() => _check = check);
      } on ApiError catch (e) {
        if (mounted) setState(() => _error = e.userMessage);
      }
    });
  }

  Future<void> _save() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final warnings = await ref
          .read(attendanceRepositoryProvider)
          .log(
            widget.bookingId,
            day: widget.day,
            minutes: _minutes,
            note: _note.text.trim(),
          );
      if (!mounted) return;
      if (warnings.isNotEmpty) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(warnings.join(' '))));
      }
      Navigator.of(context).pop(true);
    } on ApiError catch (e) {
      if (mounted) {
        setState(() {
          _saving = false;
          _error = e.userMessage;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final check = _check;
    final blocked = check != null && !check.allowed;
    return Padding(
      padding: EdgeInsets.fromLTRB(
        20,
        20,
        20,
        20 + MediaQuery.viewInsetsOf(context).bottom,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        spacing: BarterlySpace.sm,
        children: [
          Text(
            'Hours on ${DateFormat('EEE d MMM').format(widget.day)}',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          Row(
            children: [
              IconButton.outlined(
                tooltip: 'Less',
                onPressed: _minutes > 30
                    ? () {
                        setState(() => _minutes -= 30);
                        _preview();
                      }
                    : null,
                icon: const Icon(Icons.remove),
              ),
              Expanded(
                child: Text(
                  hoursLabel(_minutes),
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
              ),
              IconButton.outlined(
                tooltip: 'More',
                onPressed: _minutes < 12 * 60
                    ? () {
                        setState(() => _minutes += 30);
                        _preview();
                      }
                    : null,
                icon: const Icon(Icons.add),
              ),
            ],
          ),
          TextField(
            controller: _note,
            maxLength: 300,
            decoration: const InputDecoration(
              labelText: 'What you did (optional)',
            ),
          ),
          if (check != null) ...[
            for (final p in check.problems)
              Text(p, style: const TextStyle(color: BarterlyColors.danger)),
            for (final w in check.warnings)
              Text(w, style: Theme.of(context).textTheme.bodySmall),
          ],
          if (_error != null)
            Text(_error!, style: const TextStyle(color: BarterlyColors.danger)),
          FilledButton(
            onPressed: _saving || blocked ? null : _save,
            child: Text(_saving ? 'Saving…' : 'Save hours'),
          ),
        ],
      ),
    );
  }
}
