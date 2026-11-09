import 'package:flutter_test/flutter_test.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/core/dates.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/core/money.dart';

void main() {
  group('formatNpr matches the backend', () {
    // Same cases as backend/tests/test_money_periods_text.py
    const cases = {
      12500050: 'Rs. 1,25,000.50',
      0: 'Rs. 0',
      99: 'Rs. 0.99',
      100000: 'Rs. 1,000',
      99999900: 'Rs. 9,99,999',
      10000000000: 'Rs. 10,00,00,000',
      -150000: '-Rs. 1,500',
      54940: 'Rs. 549.40',
    };
    cases.forEach((paisa, expected) {
      test('$paisa -> $expected', () => expect(formatNpr(paisa), expected));
    });

    test('always decimals', () => expect(formatNpr(150000, alwaysDecimals: true), 'Rs. 1,500.00'));

    test('Nepali digits', () {
      expect(formatNpr(12500050, nepali: true), 'रु. १,२५,०००.५०');
      expect(toNepaliDigits('2083'), '२०८३');
    });

    test('masked text', () => expect(maskedNpr(), 'Rs. ••••'));
  });

  group('dates', () {
    test('API timestamps become Nepal wall-clock time on any phone', () {
      final instant = DateTime.parse('2026-11-08T20:22:10+05:45');
      final npt = toNepalTime(instant);
      expect((npt.year, npt.month, npt.day, npt.hour, npt.minute), (2026, 11, 8, 20, 22));
      expect(formatTime(npt), '08:22 PM');
    });

    test('day header in AD and BS', () {
      final day = DateTime.utc(2026, 11, 8);
      final ad = dayHeaderParts(day, CalendarSystem.ad);
      expect((ad.day, ad.weekday, ad.monthYear), ('8', 'Sunday', 'Nov 2026'));
      final bs = dayHeaderParts(day, CalendarSystem.bs);
      // Backend: 2026-11-09 = 2083-07-23, so the 8th is Kartik 22.
      expect((bs.day, bs.monthYear), ('22', 'Kartik 2083'));
      expect(bs.weekday, 'Sunday');
    });

    test('formatDate and apiDate', () {
      final day = DateTime.utc(2026, 11, 9);
      expect(formatDate(day, CalendarSystem.ad), '9 Nov 2026');
      expect(formatDate(day, CalendarSystem.bs), '23 Kartik 2083');
      expect(formatShortDate(day, CalendarSystem.ad), '9 Nov');
      expect(apiDate(DateTime(2026, 1, 5)), '2026-01-05');
      expect(parseApiDate('2026-11-14'), DateTime.utc(2026, 11, 14));
    });
  });
}
