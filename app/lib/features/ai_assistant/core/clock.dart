import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'dates.dart';

/// The current instant. Tests and golden images pin it, so "this month" and date pickers
/// don't move with the real date.
final clockProvider = Provider<DateTime Function()>((ref) => DateTime.now);

/// Now, in Nepal wall-clock time (see [toNepalTime]).
DateTime nepalNow(WidgetRef ref) => toNepalTime(ref.read(clockProvider)());
