import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'dates.dart';

/// Assistant preferences (edited on the settings screen in step 7).
@immutable
class AssistantPrefs {
  const AssistantPrefs({this.language = 'auto', this.calendar = CalendarSystem.ad});

  /// Reply language: 'auto' | 'en' | 'ne' | 'rom'.
  final String language;
  final CalendarSystem calendar;

  AssistantPrefs copyWith({String? language, CalendarSystem? calendar}) =>
      AssistantPrefs(language: language ?? this.language, calendar: calendar ?? this.calendar);
}

class AssistantPrefsNotifier extends Notifier<AssistantPrefs> {
  @override
  AssistantPrefs build() => const AssistantPrefs();

  void setLanguage(String language) => state = state.copyWith(language: language);
  void setCalendar(CalendarSystem calendar) => state = state.copyWith(calendar: calendar);
}

final assistantPrefsProvider = NotifierProvider<AssistantPrefsNotifier, AssistantPrefs>(
  AssistantPrefsNotifier.new,
);
