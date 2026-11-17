// The chart card for a spreadsheet added in the chat (file_report), drawn from the backend's
// own fixture: totals, the 3D pie by type, week by week bars, biggest payments, balance line.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/ai_assistant.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/chat/cards/card_views.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/chat/cards/file_report_view.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/chat/chat_models.dart';

import 'test_harness.dart';

FileReportCard _card({List<String>? sections}) {
  final json = {...fixtureCard('file_report')};
  if (sections != null) json['sections'] = sections;
  return ChatCard.fromJson(json) as FileReportCard;
}

Future<void> _pump(WidgetTester t, FileReportCard card) async {
  useSize(t, const Size(390, 2400));
  await t.pumpWidget(
    themed(
      SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: ChatCardView(card: card, messageIndex: 0, cardIndex: 0),
      ),
    ),
  );
  await t.pumpAndSettle();
}

void main() {
  test('the backend card is read with every figure', () {
    final c = _card();
    expect(c.fileName, 'statement.csv');
    expect((c.rows, c.measure, c.moneyInPaisa, c.moneyOutPaisa), (24, 'out', 1804500, 2445150));
    expect(c.start, DateTime.utc(2026, 10, 5));
    expect(c.byType.map((s) => s.label), [
      'Scan and Pay',
      'Service payment',
      'Transfer',
      'Withdraw',
    ]);
    expect(c.byType.first.sharePercent, 45.5);
    expect(c.inByType.map((s) => s.label), ['Load', 'Cashback']);
    expect(c.periods.length, 5);
    expect(c.periods[1].inPaisa, 1004500);
    expect(c.biggest.first.label, 'Fund transfer to [phone]');
    expect(c.balance.length, 24);
    expect((c.balanceCheck, c.balanceRowsChecked), ('ok', 23));
    expect(c.sections, ['types', 'periods', 'biggest', 'balance']);
  });

  testWidgets('a new file shows totals and all four charts', (t) async {
    await _pump(t, _card());
    expect(find.text('statement.csv'), findsOneWidget);
    expect(find.text('Money in'), findsWidgets);
    expect(find.text('Rs. 18,045'), findsOneWidget);
    expect(find.text('Rs. 24,451.50'), findsOneWidget);
    expect(find.text('Money out by Type'), findsOneWidget);
    expect(find.byType(Pie3D), findsOneWidget);
    for (final label in ['Scan and Pay', 'Service payment', 'Transfer', 'Withdraw']) {
      expect(find.text(label), findsOneWidget);
    }
    expect(find.text('Week by week'), findsOneWidget);
    expect(find.text('Biggest payments'), findsOneWidget);
    expect(find.text('Fund transfer to [phone]'), findsOneWidget);
    expect(find.text('Balance'), findsOneWidget);
    expect(find.textContaining('Checked row by row'), findsOneWidget);
    expect(find.text('Worked out in code from all 24 rows'), findsOneWidget);
  });

  testWidgets('a follow-up card shows only the chart asked about', (t) async {
    await _pump(t, _card(sections: ['periods']));
    expect(find.text('Week by week'), findsOneWidget);
    expect(find.byType(Pie3D), findsNothing);
    expect(find.text('Biggest payments'), findsNothing);
    expect(find.text('Rs. 24,451.50'), findsOneWidget); // the totals stay on top
  });

  testWidgets('tapping a legend row or a slice lifts that slice', (t) async {
    await _pump(t, _card());
    Pie3D pie() => t.widget<Pie3D>(find.byType(Pie3D));
    await t.tap(find.text('Transfer'));
    await t.pumpAndSettle();
    expect(pie().selected, 2);
    await t.tap(find.text('Transfer'));
    await t.pumpAndSettle();
    expect(pie().selected, isNull);

    // Right of the centre is a quarter turn from 12 o'clock: inside the first slice (45.5%).
    final box = t.getRect(find.byType(Pie3D));
    await t.tapAt(Offset(box.center.dx + 40, box.top + 74));
    await t.pumpAndSettle();
    expect(pie().selected, 0);
  });

  testWidgets('the pie switches between money out and money in', (t) async {
    await _pump(t, _card());
    await t.tap(find.bySemanticsLabel('Show money in'));
    await t.pumpAndSettle();
    expect(find.text('Money in by Type'), findsOneWidget);
    expect(find.text('Load'), findsOneWidget);
    expect(find.text('Cashback'), findsOneWidget);
    expect(find.text('99.8% · 2 rows'), findsOneWidget); // a part never shows as 100%
    expect(find.text('Scan and Pay'), findsNothing);
  });

  testWidgets('a hidden balance masks every amount in the card', (t) async {
    await _pump(t, _card());
    final container = ProviderScope.containerOf(t.element(find.byType(Scaffold)));
    container.read(amountPrivacyProvider.notifier).setHiddenByUser(true);
    await t.pumpAndSettle();
    expect(find.textContaining('24,451'), findsNothing);
    expect(find.textContaining('18,045'), findsNothing);
    expect(find.text('Rs. ••••'), findsWidgets);
  });

  testWidgets('with reduced motion the figures show at once', (t) async {
    t.platformDispatcher.accessibilityFeaturesTestValue = const FakeAccessibilityFeatures(
      disableAnimations: true,
    );
    addTearDown(t.platformDispatcher.clearAccessibilityFeaturesTestValue);
    useSize(t, const Size(390, 2400));
    await t.pumpWidget(themed(SingleChildScrollView(child: FileReportView(_card()))));
    await t.pump(); // one frame, no settling
    expect(find.text('Rs. 24,451.50'), findsOneWidget);
  });

  testWidgets('holds with large text', (t) async {
    t.platformDispatcher.textScaleFactorTestValue = 2;
    addTearDown(t.platformDispatcher.clearTextScaleFactorTestValue);
    await _pump(t, _card());
    expect(t.takeException(), isNull);
  });

  testWidgets('touch targets in the card are at least 48 px', (t) async {
    await _pump(t, _card());
    for (final f in [
      find.bySemanticsLabel('Show money in'),
      find.bySemanticsLabel('Show money out'),
      find.ancestor(of: find.text('Transfer'), matching: find.byType(InkWell)),
    ]) {
      expect(t.getSize(f.first).height, greaterThanOrEqualTo(48));
    }
  });
}
