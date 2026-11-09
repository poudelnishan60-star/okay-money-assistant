import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/core/bs_date.dart';

void main() {
  test('matches the published calendar (nepalicalendar.rat32.com, Kathmandu panchang)', () {
    expect(BsDate.fromAd(DateTime.utc(2026, 10, 18)), BsDate(2083, 7, 1)); // Kartik 1
    expect(BsDate.fromAd(DateTime.utc(2026, 11, 9)), BsDate(2083, 7, 23)); // Kartik 23
    expect(BsDate.fromAd(DateTime.utc(2026, 11, 17)), BsDate(2083, 8, 1)); // Mangsir 1
    expect(BsDate.fromAd(DateTime.utc(2027, 5, 15)), BsDate(2084, 2, 1)); // Jestha 1, 2084
    expect(BsDate.fromAd(DateTime.utc(2027, 6, 15)), BsDate(2084, 3, 1)); // Ashad 1, 2084
    expect(BsDate.daysInMonth(2083, 7), 30);
    expect(BsDate.daysInMonth(2084, 2), 31);
  });

  test('agrees with the backend (nepali-datetime) on 2,337 sample dates', () {
    final samples = (jsonDecode(
      File('test/ai_assistant/fixtures/bs_samples.json').readAsStringSync(),
    ) as List<Object?>).cast<List<Object?>>();
    expect(samples.length, greaterThan(2000));
    for (final s in samples) {
      final ad = DateTime.parse(s[0]! as String);
      final expected = BsDate(s[1]! as int, s[2]! as int, s[3]! as int);
      expect(BsDate.fromAd(ad), expected, reason: '$ad');
      expect(expected.toAd(), DateTime.utc(ad.year, ad.month, ad.day), reason: '$expected');
    }
  });

  test('names, keys and validation', () {
    final d = BsDate(2083, 7, 23);
    expect(d.monthName, 'Kartik');
    expect(d.monthNameNepali, 'कार्तिक');
    expect(d.monthKey, '2083-07');
    expect(d.toString(), '2083-07-23');
    expect(BsDate(2082, 12, 30).compareTo(BsDate(2083, 1, 1)), isNegative);
    expect(() => BsDate(2083, 7, 31), throwsRangeError); // Kartik 2083 has 30 days
    expect(() => BsDate(2083, 13, 1), throwsRangeError);
  });
}
