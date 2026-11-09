import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:khalti_ai_assistant/demo_host/web_frame.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/ai_assistant.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/chat/chat_models.dart';

import 'test_harness.dart';

Future<void> openChat(WidgetTester tester, Widget app) async {
  usePhoneSize(tester);
  await tester.pumpWidget(app);
  await tester.pumpAndSettle();
  await tester.tap(find.text('Ask me'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('empty state: mascot slot, title, 2x2 quick starts and starter chips', (t) async {
    await openChat(t, demoApp().app);
    expect(find.text('Start Chatting with O-Kay'), findsOneWidget);
    for (final label in ['My spending', 'Budgets', 'Upcoming bills', 'Savings goals']) {
      expect(find.text(label), findsOneWidget);
    }
    for (final chip in ['This month vs last', 'Where did my money go?', 'Set a food budget']) {
      expect(find.text(chip), findsOneWidget);
    }
    expect(find.text('Ask O-Kay'), findsOneWidget); // input hint
  });

  testWidgets('a quick start sends the question and streams the answer with cards', (t) async {
    final chat = FakeChatRepository([
      answer(
        'You spent Rs. 35,097.56 in October, 5.9% less than September.',
        cardTypes: ['spending_summary', 'category_breakdown'],
        suggestions: const [
          Suggestion('Where do I spend the most?'),
          Suggestion('Smart Deposit', feature: 'smart_deposit'),
        ],
      ),
    ]);
    await openChat(t, demoApp(chat: chat).app);
    await t.tap(find.text('My spending'));
    await t.pump();
    expect(find.text('How much did I spend this month?'), findsOneWidget); // user bubble
    await t.pumpAndSettle();
    expect(chat.sent.single, ('How much did I spend this month?', 'auto'));
    expect(
      find.text('You spent Rs. 35,097.56 in October, 5.9% less than September.'),
      findsOneWidget,
    );
    expect(find.text('Spent · Oct 2026'), findsOneWidget);
    expect(find.text('Where it went · Oct 2026'), findsOneWidget);
    expect(find.textContaining('transactions →'), findsWidgets);
    expect(find.text('Where do I spend the most?'), findsOneWidget); // follow-up chip row
    expect(find.text('Smart Deposit'), findsOneWidget); // feature chip under the answer
    expect(find.text('Start Chatting with O-Kay'), findsNothing);
  });

  testWidgets('tool status shows while waiting for the first word', (t) async {
    final hold = Completer<void>();
    final chat = FakeChatRepository([
      [const ToolStatusEvent('get_recurring_payments')],
    ])..holdOpen = hold;
    await openChat(t, demoApp(chat: chat).app);
    await t.enterText(find.byType(TextField), 'bills?');
    await t.pump();
    await t.tap(find.bySemanticsLabel('Send'));
    await t.pump(const Duration(milliseconds: 50));
    await t.pump(const Duration(milliseconds: 50));
    expect(find.text('Finding your bills…'), findsOneWidget);
    hold.complete();
    await t.pumpAndSettle();
  });

  testWidgets('a reset replaces the half-streamed text with the corrected answer', (t) async {
    final chat = FakeChatRepository([
      [
        const TokenEvent('I made up Rs. 9,999.'),
        const ResetEvent(),
        ...answer('You spent Rs. 1,270 on food.'),
      ],
    ]);
    await openChat(t, demoApp(chat: chat).app);
    await t.tap(find.text('My spending'));
    await t.pumpAndSettle();
    expect(find.textContaining('9,999'), findsNothing);
    expect(find.text('You spent Rs. 1,270 on food.'), findsOneWidget);
  });

  testWidgets('confirm card saves only on Confirm', (t) async {
    final chat = FakeChatRepository([
      answer('Tap Confirm to save it.', cardTypes: ['confirm_action']),
    ]);
    await openChat(t, demoApp(chat: chat).app);
    await t.ensureVisible(find.text('Set a food budget'));
    await t.tap(find.text('Set a food budget'));
    await t.pumpAndSettle();
    expect(find.text('Set Food & Dining budget'), findsOneWidget);
    expect(chat.confirmed, isEmpty);
    await t.ensureVisible(find.text('Confirm'));
    await t.tap(find.text('Confirm'));
    await t.pumpAndSettle();
    expect(chat.confirmed.single.path, '/budgets');
    expect(chat.confirmed.single.body['limit_paisa'], 600000);
    expect(find.text('Saved'), findsOneWidget);
  });

  testWidgets('a failed confirm shows the reason and can be retried', (t) async {
    final chat = FakeChatRepository([
      answer('Tap Confirm to save it.', cardTypes: ['confirm_action']),
    ])..confirmError = const ApiException('Input should be greater than 0', statusCode: 422);
    await openChat(t, demoApp(chat: chat).app);
    await t.ensureVisible(find.text('Set a food budget'));
    await t.tap(find.text('Set a food budget'));
    await t.pumpAndSettle();
    await t.ensureVisible(find.text('Confirm'));
    await t.tap(find.text('Confirm'));
    await t.pumpAndSettle();
    expect(find.text('Input should be greater than 0'), findsOneWidget);
    expect(find.text('Try again'), findsOneWidget);
  });

  testWidgets('open_app_flow card opens the host flow pre-filled (no money moves)', (t) async {
    final chat = FakeChatRepository([
      answer('Tap the button below.', cardTypes: ['open_app_flow']),
    ]);
    final demo = demoApp(chat: chat);
    await openChat(t, demo.app);
    await t.enterText(find.byType(TextField), 'Pay my electricity bill');
    await t.pump();
    await t.tap(find.bySemanticsLabel('Send'));
    await t.pumpAndSettle();
    expect(find.text('Rs. 1,140.67'), findsWidgets);
    await t.ensureVisible(find.widgetWithText(FilledButton, 'Pay electricity bill'));
    await t.tap(find.widgetWithText(FilledButton, 'Pay electricity bill'));
    await t.pumpAndSettle();
    expect(demo.bridge.calls, ['openBillPayment:electricity']);
    expect(find.text('Would open Bill Payment (electricity)'), findsOneWidget);
  });

  testWidgets('hidden balance masks amounts in the answer text and cards', (t) async {
    final chat = FakeChatRepository([
      answer('You spent **Rs. 1,270** on food.', cardTypes: ['spending_summary']),
    ]);
    await openChat(t, demoApp(chat: chat).app);
    final container = ProviderScope.containerOf(t.element(find.byType(Scaffold).first));
    container.read(amountPrivacyProvider.notifier).setHiddenByUser(true);
    await t.tap(find.text('My spending'));
    await t.pumpAndSettle();
    expect(find.textContaining('1,270'), findsNothing);
    expect(find.textContaining('Rs. ••••'), findsWidgets);
    await t.tap(find.textContaining('You spent'));
    await t.pumpAndSettle();
    expect(find.text('You spent Rs. 1,270 on food.'), findsOneWidget); // bold markers gone
  });

  testWidgets('errors offer Try again, which re-asks the question', (t) async {
    final chat = FakeChatRepository([
      [
        const TokenEvent('O-Kay is busy, please try again in a minute.'),
        const DoneEvent(messageId: 1, cards: [], suggestions: [], language: 'en', error: 'busy'),
      ],
      answer('Here it is.'),
    ]);
    await openChat(t, demoApp(chat: chat).app);
    await t.tap(find.text('Budgets'));
    await t.pumpAndSettle();
    expect(find.text('O-Kay is busy, please try again in a minute.'), findsOneWidget);
    await t.tap(find.text('Try again'));
    await t.pumpAndSettle();
    expect(chat.sent.map((s) => s.$1), ['Show my budgets', 'Show my budgets']);
    expect(find.text('Here it is.'), findsOneWidget);
  });

  testWidgets('rate limit from the server is shown as an answer, not a crash', (t) async {
    final chat = FakeChatRepository()
      ..sendError = const ApiException(
        "You're sending messages quickly. Please wait a moment and try again.",
        statusCode: 429,
      );
    await openChat(t, demoApp(chat: chat).app);
    await t.tap(find.text('Budgets'));
    await t.pumpAndSettle();
    expect(find.textContaining("You're sending messages quickly"), findsOneWidget);
  });

  testWidgets('thumbs up is sent and toggles off', (t) async {
    final chat = FakeChatRepository([answer('Done.', id: 42)]);
    await openChat(t, demoApp(chat: chat).app);
    await t.tap(find.text('Budgets'));
    await t.pumpAndSettle();
    await t.tap(find.byTooltip('Helpful'));
    await t.pumpAndSettle();
    await t.tap(find.byTooltip('Helpful'));
    await t.pumpAndSettle();
    expect(chat.feedback, [(42, 'up'), (42, null)]);
  });

  testWidgets('"View N transactions" opens the transactions screen with the filters', (t) async {
    final chat = FakeChatRepository([
      answer('Here are your transactions.', cardTypes: ['transactions_preview']),
    ]);
    await openChat(t, demoApp(chat: chat).app);
    await t.tap(find.text('My spending'));
    await t.pumpAndSettle();
    final link = find.textContaining('transactions →');
    await t.ensureVisible(link);
    await t.tap(link);
    await t.pumpAndSettle();
    expect(find.textContaining('Will open filtered by: start=2026-11-03'), findsOneWidget);
  });

  testWidgets('history loads when the chat opens; clear asks first', (t) async {
    final chat = FakeChatRepository()
      ..historyMessages = [
        const ChatMessage(role: MessageRole.user, text: 'old question', id: 1),
        const ChatMessage(role: MessageRole.assistant, text: 'old answer', id: 2),
      ];
    await openChat(t, demoApp(chat: chat).app);
    expect(find.text('old answer'), findsOneWidget);
    await t.tap(find.byTooltip('Clear chat'));
    await t.pumpAndSettle();
    await t.tap(find.text('Clear chat').last);
    await t.pumpAndSettle();
    expect(chat.cleared, isTrue);
    expect(find.text('Start Chatting with O-Kay'), findsOneWidget);
  });

  group('website frame', () {
    testWidgets('desktop: centred phone-width column with the unofficial label', (t) async {
      useSize(t, const Size(1280, 800));
      await t.pumpWidget(demoApp().app);
      await t.pumpAndSettle();
      expect(find.text(WebFrame.unofficialLabel), findsOneWidget);
      final home = t.getRect(find.byType(Navigator).first);
      expect(home.width, WebFrame.maxWidth);
      expect(home.center.dx, closeTo(640, 1));
    });

    testWidgets('phone: full width, label still on every screen', (t) async {
      usePhoneSize(t);
      final demo = demoApp();
      await t.pumpWidget(demo.app);
      await t.pumpAndSettle();
      expect(t.getRect(find.byType(Navigator).first).width, 390);
      GoRouter.of(t.element(find.text('Financial Services'))).go(OkayRoutes.chat);
      await t.pumpAndSettle();
      expect(find.text(WebFrame.unofficialLabel), findsOneWidget);
    });
  });
}
