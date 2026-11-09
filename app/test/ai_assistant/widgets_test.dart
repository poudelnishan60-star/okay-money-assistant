import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/ai_assistant.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/core/dates.dart';

import 'test_harness.dart';

void main() {
  group('AmountText and balance privacy', () {
    testWidgets('shows the amount when not hidden', (tester) async {
      await tester.pumpWidget(themed(const AmountText(12500050)));
      expect(find.text('Rs. 1,25,000.50'), findsOneWidget);
    });

    testWidgets('masks every amount until one is tapped', (tester) async {
      late WidgetRef ref;
      await tester.pumpWidget(
        themed(
          Consumer(
            builder: (context, r, _) {
              ref = r;
              return const Column(children: [AmountText(150000), AmountText(2394486)]);
            },
          ),
        ),
      );
      ref.read(amountPrivacyProvider.notifier).setHiddenByUser(true);
      await tester.pump();
      expect(find.text('Rs. ••••'), findsNWidgets(2));
      expect(find.text('Rs. 1,500'), findsNothing);

      await tester.tap(find.text('Rs. ••••').first);
      await tester.pump();
      expect(find.text('Rs. 1,500'), findsOneWidget);
      expect(find.text('Rs. 23,944.86'), findsOneWidget); // all revealed together

      // Hiding again in the host masks them again.
      ref.read(amountPrivacyProvider.notifier).setHiddenByUser(true);
      await tester.pump();
      expect(find.text('Rs. ••••'), findsNWidgets(2));
    });

    testWidgets('direction arrows: pink down for debit, green up for credit', (tester) async {
      await tester.pumpWidget(
        themed(
          const Column(
            children: [
              AmountText(100, isDebit: true, showArrow: true),
              AmountText(100, isDebit: false, showArrow: true),
            ],
          ),
        ),
      );
      final icons = tester.widgetList<Icon>(find.byType(Icon)).toList();
      expect(icons[0].icon, Icons.south_rounded);
      expect(icons[0].color, OkayColors.accentPink);
      expect(icons[1].icon, Icons.north_rounded);
      expect(icons[1].color, OkayColors.positive);
    });
  });

  test('budget colours: green < 80%, amber 80-100%, red > 100%', () {
    expect(budgetColor(79.9), OkayColors.positive);
    expect(budgetColor(80), OkayColors.warning);
    expect(budgetColor(100), OkayColors.warning);
    expect(budgetColor(100.1), OkayColors.danger);
  });

  testWidgets('period chips report the chosen period', (tester) async {
    PeriodChoice? chosen;
    await tester.pumpWidget(
      themed(PeriodChips(selected: PeriodChoice.days7, onChanged: (p) => chosen = p)),
    );
    for (final label in ['7 days', '14 days', '30 days', 'This month', 'Custom']) {
      expect(find.text(label), findsOneWidget);
    }
    await tester.tap(find.text('30 days'));
    expect(chosen, PeriodChoice.days30);
    expect(PeriodChoice.thisMonth.apiValue, 'this_month');
    expect(PeriodChoice.custom.apiValue, isNull);
  });

  testWidgets('transaction row and day header', (tester) async {
    await tester.pumpWidget(
      themed(
        Column(
          children: [
            DateGroupHeader(date: DateTime.utc(2026, 11, 8), closingBalancePaisa: 2394486),
            TransactionRow(
              icon: Icons.qr_code_scanner_outlined,
              title: 'Scan and Pay',
              merchant: 'Ratna Mart',
              reference: 'K7Q2M9XH4TB',
              nepalTime: DateTime.utc(2026, 11, 8, 20, 22),
              amountPaisa: 184735,
              isDebit: true,
            ),
          ],
        ),
      ),
    );
    expect(find.text('8'), findsOneWidget);
    expect(find.text('Sunday'), findsOneWidget);
    expect(find.text('Nov 2026'), findsOneWidget);
    expect(find.text('Closing Balance'), findsOneWidget);
    expect(find.text('Rs. 23,944.86'), findsOneWidget);
    expect(find.text('Ratna Mart | K7Q2M9XH4TB'), findsOneWidget);
    expect(find.text('08:22 PM'), findsOneWidget);
    expect(find.text('Rs. 1,847.35'), findsOneWidget);
  });

  testWidgets('BS day header', (tester) async {
    await tester.pumpWidget(
      themed(
        DateGroupHeader(
          date: DateTime.utc(2026, 11, 8),
          closingBalancePaisa: null,
          calendar: CalendarSystem.bs,
        ),
      ),
    );
    expect(find.text('22'), findsOneWidget);
    expect(find.text('Kartik 2083'), findsOneWidget);
    expect(find.text('Closing Balance'), findsNothing);
  });

  test('transaction visuals cover every backend type', () {
    for (final type in [
      'scan_pay',
      'bill_payment',
      'topup',
      'transfer',
      'remittance',
      'booking',
      'deposit',
    ]) {
      expect(transactionVisual(type, null).title, isNot('Transaction'));
    }
    expect(transactionVisual('bill_payment', 'electricity').title, 'Electricity Payment');
  });

  group('MockHostAppBridge', () {
    testWidgets('shows a "would open" sheet with the prefill', (tester) async {
      final key = GlobalKey<NavigatorState>();
      final bridge = MockHostAppBridge(key);
      await tester.pumpWidget(
        MaterialApp(navigatorKey: key, theme: buildOkayTheme(), home: const Scaffold()),
      );
      final done = bridge.openBillPayment(
        'electricity',
        const BillPaymentPrefill(billerName: 'Nepal Electricity Authority', amountPaisa: 114067),
      );
      await tester.pumpAndSettle();
      expect(find.text('Would open Bill Payment (electricity)'), findsOneWidget);
      expect(find.text('Nepal Electricity Authority'), findsOneWidget);
      expect(find.text('Rs. 1,140.67'), findsOneWidget);
      await tester.tap(find.text('OK'));
      await tester.pumpAndSettle();
      await done;
      expect(bridge.calls, ['openBillPayment:electricity']);
    });

    testWidgets('authenticate returns the user choice', (tester) async {
      final key = GlobalKey<NavigatorState>();
      final bridge = MockHostAppBridge(key);
      await tester.pumpWidget(MaterialApp(navigatorKey: key, home: const Scaffold()));

      final approved = bridge.authenticate(reason: 'Save budget');
      await tester.pumpAndSettle();
      await tester.tap(find.text('Approve (mock)'));
      await tester.pumpAndSettle();
      expect(await approved, isTrue);

      final cancelled = bridge.authenticate(reason: 'Save budget');
      await tester.pumpAndSettle();
      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();
      expect(await cancelled, isFalse);
    });
  });
}
