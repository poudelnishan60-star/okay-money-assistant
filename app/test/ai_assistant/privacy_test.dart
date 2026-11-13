import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/ai_assistant.dart';

import 'test_harness.dart';

/// Balance privacy: with amounts hidden, nothing on any assistant screen shows a figure.
/// Uses the bundled fonts, so cards lay out as they do for real.
void main() {
  setUpAll(loadAppFonts);

  testWidgets('hidden amounts are masked in the chat and on every screen', (t) async {
    useSize(t, const Size(390, 4000));
    final chat = FakeChatRepository([
      answer(
        'You spent Rs. 6,213.80 so far this month.',
        cardTypes: ['spending_summary', 'category_breakdown', 'budget_progress', 'bills_list'],
      ),
    ]);
    await t.pumpWidget(demoApp(chat: chat).app);
    await t.pumpAndSettle();
    await t.tap(find.text('My spending'));
    await t.pumpAndSettle();
    final amount = RegExp(r'(?:Rs\.?|रु\.?)\s?[\d०-९]');
    List<String> leaks() => [
      for (final e in find.byType(RichText).evaluate()) (e.widget as RichText).text.toPlainText(),
    ].where(amount.hasMatch).toList();
    expect(leaks(), isNotEmpty, reason: 'the check must see amounts while they are shown');
    await hideAmounts(t);
    expect(leaks(), isEmpty, reason: 'chat answer and cards');
    final router = routerOf(t);
    for (final path in [
      OkayRoutes.insights,
      OkayRoutes.transactions,
      OkayRoutes.budgets,
      OkayRoutes.goals,
      OkayRoutes.bills,
      OkayRoutes.alerts,
      OkayRoutes.settings,
    ]) {
      unawaited(router.push(path));
      await t.pumpAndSettle();
      expect(leaks(), isEmpty, reason: path);
      router.pop();
      await t.pumpAndSettle();
    }
  });
}
