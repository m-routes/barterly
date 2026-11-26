import 'package:add_2_calendar/add_2_calendar.dart' as cal;
import 'package:flutter/foundation.dart';

/// An event to put in the phone's own calendar, with a reminder before it.
@immutable
class CalendarEvent {
  const new({
    required this.title,
    required this.start,
    required this.end,
    this.description = '',
    this.location = '',
    this.allDay = false,
    this.remindBefore = const Duration(minutes: 30),
    this.url = '',
  });

  final String title;
  final DateTime start;
  final DateTime end;
  final String description;
  final String location;
  final bool allDay;
  final Duration remindBefore;
  final String url;
}

/// Adds events to the device calendar. The phone's own calendar opens with the
/// event filled in and the person confirms it, so no calendar permission is
/// needed.
abstract interface class CalendarService {
  /// False when no calendar app could take it.
  Future<bool> add(CalendarEvent event);
}

class DeviceCalendar implements CalendarService {
  const new();

  @override
  Future<bool> add(CalendarEvent event) => cal.Add2Calendar.addEvent2Cal(
    cal.Event(
      title: event.title,
      description: event.description,
      location: event.location,
      startDate: event.start,
      endDate: event.end,
      allDay: event.allDay,
      timeZone: 'Asia/Kolkata',
      // iOS takes the alarm from here; Android's calendar app applies its own
      // default reminder, which the person can change before saving.
      iosParams: cal.IOSParams(
        reminder: event.remindBefore,
        url: event.url.isEmpty ? null : event.url,
      ),
    ),
  );
}
