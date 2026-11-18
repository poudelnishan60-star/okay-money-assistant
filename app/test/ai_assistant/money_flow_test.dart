// The money-flow diagram (money in by source -> wallet -> money out by use), from the
// backend's own fixture for the account's last 30 days.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/ai_assistant.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/chat/cards/card_views.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/chat/chat_models.dart';

import 'test_harness.dart';

MoneyFlowCard _card() => ChatCard.fromJson(fixtureCard('money_flow')) as MoneyFlowCard;

Future<void> _pump(WidgetTester t) async {
  useSize(t, const Size(390, 1200));
  await t.pumpWidget(
    themed(
      SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: ChatCardView(card: _card(), messageIndex: 0, cardIndex: 0),
      ),
    ),
  );
  await t.pumpAndSettle();
}

/// The labels of one side never overlap: each sits in its own row beside its own bar.
void _labelsApart(WidgetTester t, List<String> labels) {
  final rects = [for (final l in labels) t.getRect(find.text(l))];
  for (var i = 1; i < rects.length; i++) {
    expect(rects[i].top, greaterThanOrEqualTo(rects[i - 1].bottom), reason: labels[i]);
  }
}

void main() {
  test('the backend card is read: both sides add up to the same total', () {
    final c = _card();
    expect(c.periodLabel, 'Last 30 days');
    expect(c.flow.sources.map((i) => i.label), ['Remittance', 'Transfers in']);
    expect(c.flow.uses.map((i) => i.kind).toSet(), {'out', 'moved', 'balance'});
    expect(c.flow.uses.last.label, 'Left over');
    int sum(List<FlowItem> items) => items.fold(0, (a, i) => a + i.paisa);
    expect(sum(c.flow.sources), sum(c.flow.uses));
    expect(sum(c.flow.sources), c.flow.moneyInPaisa); // more came in than went out
  });

  testWidgets('every source and use is labelled with its amount, with a legend', (t) async {
    await _pump(t);
    final c = _card();
    expect(find.text('Money in and out · Last 30 days'), findsOneWidget);
    expect(find.text('Wallet'), findsOneWidget);
    for (final i in [...c.flow.sources, ...c.flow.uses]) {
      expect(find.text(i.label), findsOneWidget);
      expect(find.text(formatNpr(i.paisa)), findsWidgets);
    }
    for (final words in ['Money in', 'Spent', 'Sent and saved', 'Balance']) {
      expect(find.text(words), findsOneWidget);
    }
    expect(find.textContaining('transactions →'), findsOneWidget);
    _labelsApart(t, [for (final i in c.flow.uses) i.label]);
  });

  testWidgets('screen readers get the whole flow in words', (t) async {
    await _pump(t);
    expect(find.bySemanticsLabel(RegExp(r'^Money flow\. Came from: Remittance Rs\.')), findsOne);
  });

  testWidgets('a hidden balance masks the amounts in the diagram', (t) async {
    await _pump(t);
    final container = ProviderScope.containerOf(t.element(find.byType(Scaffold)));
    container.read(amountPrivacyProvider.notifier).setHiddenByUser(true);
    await t.pumpAndSettle();
    expect(find.textContaining('27,500'), findsNothing);
    expect(find.text('Rs. ••••'), findsWidgets);
  });

  testWidgets('holds with large text: rows grow, labels stay apart', (t) async {
    t.platformDispatcher.textScaleFactorTestValue = 2;
    addTearDown(t.platformDispatcher.clearTextScaleFactorTestValue);
    await _pump(t);
    expect(t.takeException(), isNull);
    _labelsApart(t, [for (final i in _card().flow.uses) i.label]);
  });
}
