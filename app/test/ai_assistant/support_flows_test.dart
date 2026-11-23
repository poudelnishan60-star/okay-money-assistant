import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/ai_assistant.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/chat/chat_models.dart';

import 'test_harness.dart';

/// Step 11: the new app flows (split a bill, support, block the wallet, load money) open the
/// host's own screens and never move money; transactions show their status in words; and
/// "Get help" asks O-Kay about a failed or pending one.

/// An answer whose card is the backend's own open_app_flow card for [flow].
List<ChatStreamEvent> flowAnswer(String flow) => [
  const TokenEvent('Tap the button below.'),
  DoneEvent(
    messageId: 9,
    cards: [
      ChatCard.fromJson(
        fixtureCards().firstWhere((c) => c['type'] == 'open_app_flow' && c['flow'] == flow),
      ),
    ],
    suggestions: const [],
    language: 'en',
  ),
];

Future<void> ask(WidgetTester t, String text) async {
  await t.enterText(find.byType(TextField), text);
  await t.pump();
  await t.tap(find.bySemanticsLabel('Send'));
  await t.pumpAndSettle();
}

Future<void> tapButton(WidgetTester t, String label) async {
  final button = find.widgetWithText(FilledButton, label);
  await t.ensureVisible(button);
  await t.tap(button);
  await t.pumpAndSettle();
}

void main() {
  group('new app flows', () {
    for (final (flow, question, button, call, sheet) in [
      (
        'request_money',
        'split Rs. 1,000 dinner between 3',
        'Split the bill',
        'openRequestMoney',
        'Would open Request Money',
      ),
      (
        'support',
        'talk to a person',
        'Contact Khalti support',
        'openSupport:',
        'Would open Khalti Support',
      ),
      (
        'block_wallet',
        'I lost my phone',
        'Block my wallet',
        'openWalletSecurity',
        'Would open Security: Block Wallet',
      ),
      (
        'load_money',
        'load Rs. 5,000 from my bank',
        'Load money from bank',
        'openLoadMoney',
        'Would open Load Money',
      ),
    ]) {
      testWidgets('$flow opens the host screen (no money moves)', (t) async {
        final demo = demoApp(chat: FakeChatRepository([flowAnswer(flow)]));
        usePhoneSize(t);
        await t.pumpWidget(demo.app);
        await t.pumpAndSettle();
        await ask(t, question);
        await tapButton(t, button);
        expect(demo.bridge.calls.single, startsWith(call));
        expect(find.text(sheet), findsOneWidget);
      });
    }

    testWidgets('a split bill shows each share, worked out by the backend', (t) async {
      final demo = demoApp(chat: FakeChatRepository([flowAnswer('request_money')]));
      usePhoneSize(t);
      await t.pumpWidget(demo.app);
      await t.pumpAndSettle();
      await ask(t, 'split Rs. 1,000 dinner between 3');
      expect(find.text('3 people, you too'), findsOneWidget);
      expect(find.text('Sita'), findsOneWidget);
      expect(find.text('Ram'), findsOneWidget);
      expect(find.text('Rs. 333.33'), findsNWidgets(2));
      expect(find.text('Your share'), findsOneWidget);
      expect(find.text('Rs. 333.34'), findsOneWidget); // the leftover paisa is the user's
    });

    testWidgets('support shows the transaction it attaches', (t) async {
      final demo = demoApp(chat: FakeChatRepository([flowAnswer('support')]));
      usePhoneSize(t);
      await t.pumpWidget(demo.app);
      await t.pumpAndSettle();
      await ask(t, 'my topup failed');
      expect(find.text('Nepal Telecom · Rs. 500 · 05 Nov 2026 · failed'), findsOneWidget);
      expect(find.text('Topup failed'), findsOneWidget);
    });
  });

  group('transaction status', () {
    Future<FakeChatRepository> openTransactions(WidgetTester t) async {
      useSize(t, const Size(390, 1600));
      final chat = FakeChatRepository([answer('It failed; the refund is overdue.')]);
      final demo = demoApp(chat: chat);
      await t.pumpWidget(demo.app);
      await t.pumpAndSettle();
      unawaited(routerOf(t).push(OkayRoutes.transactions));
      await t.pumpAndSettle();
      return chat;
    }

    testWidgets('rows say Pending and Failed in words', (t) async {
      await openTransactions(t);
      expect(find.text('Pending'), findsOneWidget);
      expect(find.text('Failed'), findsOneWidget);
    });

    testWidgets('a failed one explains itself and Get help asks O-Kay about it', (t) async {
      final chat = await openTransactions(t);
      await t.ensureVisible(find.text('Failed'));
      await t.tap(find.text('Failed'));
      await t.pumpAndSettle();
      expect(find.text("The money left your wallet and hasn't come back yet."), findsOneWidget);
      await t.ensureVisible(find.text('Get help'));
      await t.tap(find.text('Get help'));
      await t.pumpAndSettle();
      final (question, _) = chat.sent.single;
      expect(question, startsWith('What happened to my failed payment to Nepal Telecom on 5 Nov'));
      expect(question, contains('Transaction ID: txn_'));
      expect(find.text('It failed; the refund is overdue.'), findsOneWidget); // in the chat
    });

    testWidgets('a completed one has no Get help', (t) async {
      await openTransactions(t);
      await t.tap(find.textContaining('Sasto Mitho Khaja Ghar').first);
      await t.pumpAndSettle();
      expect(find.text('Get help'), findsNothing);
      expect(find.text('Status'), findsNothing);
    });
  });
}
