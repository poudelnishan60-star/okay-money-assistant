/// Dates in Nepal time, shown in AD (default) or BS.
///
/// The API sends timestamps with the Nepal offset (+05:45). Dart parses them into an instant;
/// [toNepalTime] turns that instant back into Nepal wall-clock fields, whatever the phone's
/// own time zone is.
library;

import 'package:intl/intl.dart';

import 'bs_date.dart';

enum CalendarSystem { ad, bs }

const nepalOffset = Duration(hours: 5, minutes: 45);

/// Nepal wall-clock time for an instant (returned as a UTC DateTime whose fields read as NPT).
DateTime toNepalTime(DateTime instant) => instant.toUtc().add(nepalOffset);

/// Parses an API date 'YYYY-MM-DD' as a plain calendar date.
DateTime parseApiDate(String value) {
  final d = DateTime.parse(value);
  return DateTime.utc(d.year, d.month, d.day);
}

/// 'YYYY-MM-DD' for query parameters.
String apiDate(DateTime date) =>
    '${date.year.toString().padLeft(4, '0')}-${date.month.toString().padLeft(2, '0')}-'
    '${date.day.toString().padLeft(2, '0')}';

/// The pieces of a transaction-list day header: big day number, weekday, 'Mon YYYY'.
class DayHeaderParts {
  const DayHeaderParts(this.day, this.weekday, this.monthYear);
  final String day;
  final String weekday;
  final String monthYear;
}

String _weekday(DateTime date) => DateFormat('EEEE').format(date);

DayHeaderParts dayHeaderParts(DateTime date, CalendarSystem calendar) {
  if (calendar == CalendarSystem.bs) {
    final bs = BsDate.fromAd(date);
    return DayHeaderParts('${bs.day}', _weekday(date), '${bs.monthName} ${bs.year}');
  }
  return DayHeaderParts('${date.day}', _weekday(date), DateFormat('MMM yyyy').format(date));
}

/// '9 Nov 2026' / '23 Kartik 2083'.
String formatDate(DateTime date, CalendarSystem calendar) {
  if (calendar == CalendarSystem.bs) {
    final bs = BsDate.fromAd(date);
    return '${bs.day} ${bs.monthName} ${bs.year}';
  }
  return DateFormat('d MMM yyyy').format(date);
}

/// '9 Nov' / '23 Kartik' (no year).
String formatShortDate(DateTime date, CalendarSystem calendar) {
  if (calendar == CalendarSystem.bs) {
    final bs = BsDate.fromAd(date);
    return '${bs.day} ${bs.monthName}';
  }
  return DateFormat('d MMM').format(date);
}

/// '08:22 PM' from Nepal wall-clock fields.
String formatTime(DateTime nepalTime) => DateFormat('hh:mm a').format(nepalTime);
