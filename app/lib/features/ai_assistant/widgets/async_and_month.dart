import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/api_client.dart';
import '../core/bs_date.dart';
import '../core/dates.dart';
import '../theme/okay_theme.dart';
import 'scaffold_and_states.dart';

/// Loading / error-with-retry / data for an AsyncValue.
class AsyncBody<T> extends StatelessWidget {
  const AsyncBody({super.key, required this.value, required this.data, required this.onRetry});

  final AsyncValue<T> value;
  final Widget Function(T data) data;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return switch (value) {
      AsyncData(:final value) => data(value),
      AsyncError(:final error) => ErrorView(
        message: error is ApiException ? error.message : 'Something went wrong.',
        onRetry: onRetry,
      ),
      _ => const LoadingView(),
    };
  }
}

/// A month in the chosen calendar, as the API's month=... key ('2026-11' AD, '2083-07' BS).
@immutable
class MonthRef {
  const MonthRef(this.year, this.month, this.calendar);

  factory MonthRef.containing(DateTime day, CalendarSystem calendar) {
    if (calendar == CalendarSystem.bs) {
      final bs = BsDate.fromAd(day);
      return MonthRef(bs.year, bs.month, calendar);
    }
    return MonthRef(day.year, day.month, calendar);
  }

  final int year;
  final int month;
  final CalendarSystem calendar;

  String get key => '$year-${month.toString().padLeft(2, '0')}';
  String get calendarParam => calendar == CalendarSystem.bs ? 'BS' : 'AD';

  MonthRef shift(int delta) {
    final index = year * 12 + (month - 1) + delta;
    return MonthRef(index ~/ 12, index % 12 + 1, calendar);
  }

  bool isAfter(MonthRef other) => year * 12 + month > other.year * 12 + other.month;

  @override
  bool operator ==(Object other) =>
      other is MonthRef && other.year == year && other.month == month && other.calendar == calendar;

  @override
  int get hashCode => Object.hash(year, month, calendar);
}

/// "‹  Nov 2026  ›": previous / next month; can't go past the current month.
class MonthSelector extends StatelessWidget {
  const MonthSelector({
    super.key,
    required this.month,
    required this.current,
    required this.label,
    required this.onChanged,
  });

  final MonthRef month;
  final MonthRef current;

  /// The period label from the API ('Nov 2026', 'Kartik 2083').
  final String label;
  final ValueChanged<MonthRef> onChanged;

  @override
  Widget build(BuildContext context) {
    final canGoForward = current.isAfter(month);
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        IconButton(
          tooltip: 'Previous month',
          onPressed: () => onChanged(month.shift(-1)),
          icon: const Icon(Icons.chevron_left_rounded),
        ),
        Flexible(
          child: Text(label, style: OkayText.rowTitle, textAlign: TextAlign.center),
        ),
        IconButton(
          tooltip: 'Next month',
          onPressed: canGoForward ? () => onChanged(month.shift(1)) : null,
          icon: const Icon(Icons.chevron_right_rounded),
        ),
      ],
    );
  }
}
