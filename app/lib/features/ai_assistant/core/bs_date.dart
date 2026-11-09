/// Bikram Sambat dates, from the same calendar table the backend uses (bs_calendar_data.dart
/// is generated from nepali-datetime), so app and backend never disagree about a BS date.
library;

import 'package:flutter/foundation.dart';

import 'bs_calendar_data.dart';

@immutable
class BsDate implements Comparable<BsDate> {
  BsDate(this.year, this.month, this.day) {
    if (year < bsFirstYear || year > bsLastYear) {
      throw RangeError.range(year, bsFirstYear, bsLastYear, 'year');
    }
    RangeError.checkValueInInterval(month, 1, 12, 'month');
    RangeError.checkValueInInterval(day, 1, daysInMonth(year, month), 'day');
  }

  /// The BS date of an AD calendar date (only the date fields of [ad] are used).
  factory BsDate.fromAd(DateTime ad) {
    var days = DateTime.utc(ad.year, ad.month, ad.day).difference(bsEpochAd).inDays;
    if (days < 0) throw RangeError('$ad is before BS $bsFirstYear');
    for (var y = bsFirstYear; y <= bsLastYear; y++) {
      final months = bsMonthLengths[y]!;
      for (var m = 0; m < 12; m++) {
        if (days < months[m]) return BsDate(y, m + 1, days + 1);
        days -= months[m];
      }
    }
    throw RangeError('$ad is after BS $bsLastYear');
  }

  final int year;
  final int month;
  final int day;

  static int daysInMonth(int year, int month) => bsMonthLengths[year]![month - 1];

  int get daysInThisMonth => daysInMonth(year, month);

  /// The AD date (UTC midnight).
  DateTime toAd() {
    var days = day - 1;
    for (var y = bsFirstYear; y < year; y++) {
      days += bsMonthLengths[y]!.fold(0, (a, b) => a + b);
    }
    for (var m = 1; m < month; m++) {
      days += daysInMonth(year, m);
    }
    return bsEpochAd.add(Duration(days: days));
  }

  String get monthName => bsMonthNames[month - 1];
  String get monthNameNepali => bsMonthNamesNepali[month - 1];

  /// 'YYYY-MM' key, as the API's month=... parameter expects for calendar=BS.
  String get monthKey => '$year-${month.toString().padLeft(2, '0')}';

  @override
  int compareTo(BsDate other) => year != other.year
      ? year - other.year
      : (month != other.month ? month - other.month : day - other.day);

  @override
  bool operator ==(Object other) =>
      other is BsDate && other.year == year && other.month == month && other.day == day;

  @override
  int get hashCode => Object.hash(year, month, day);

  /// '2083-07-23' (same as the backend's to_bs_string).
  @override
  String toString() =>
      '$year-${month.toString().padLeft(2, '0')}-${day.toString().padLeft(2, '0')}';
}
