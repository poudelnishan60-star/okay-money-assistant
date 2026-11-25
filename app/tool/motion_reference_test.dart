// High-resolution reference images of O-Kay for a motion-graphics video:
//   screens/  phone screens at 3x: 1179 x 2556 px (an iPhone 15 Pro, 393 x 852 points)
//   tall/     whole pages and a whole conversation at 3x, for scrolling shots
//   parts/    each chat card and the "Ask me" button alone at 4x, on a transparent background
//
//   cd app
//   flutter test tool/motion_reference_test.dart
//   python tool/motion_reference_finish.py      # trims the tall pages, makes contact.png
//
// Written to ../motion-reference/ (kept out of git). Scripted chats with the backend's real
// card data; no network. Not part of `flutter test` (that only runs test/).
library;

import 'dart:async';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/ai_assistant.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/chat/cards/card_views.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/chat/chat_models.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/core/clock.dart';

import '../test/ai_assistant/test_harness.dart';

const _phone = Size(393, 852);
const _tall = Size(393, 3000);
const _screenScale = 3.0;
const _partScale = 4.0;
const _out = '../../motion-reference';
const _support =
    '**Khalti support:** 01-5970017 · toll-free 16600158888 (NTC) · WhatsApp/Viber '
    '+977 9801165561 · support@khalti.com';

var _ids = 100;

Future<void> _pump(
  WidgetTester t, {
  FakeChatRepository? chat,
  FakeFileSource? files,
  Size size = _phone,
}) async {
  t.view.physicalSize = size * _screenScale;
  t.view.devicePixelRatio = _screenScale;
  addTearDown(t.view.reset);
  final demo = demoApp(chat: chat, files: files);
  await t.pumpWidget(demo.app);
  await t.pumpAndSettle();
  await loadMascot(t);
}

Future<void> _shot(String name) =>
    expectLater(find.byType(MaterialApp).first, matchesGoldenFile('$_out/$name.png'));

Future<void> _frames(WidgetTester t, [int n = 8]) async {
  for (var i = 0; i < n; i++) {
    await t.pump(const Duration(milliseconds: 100));
  }
}

Future<void> _ask(WidgetTester t, String question, {bool settle = true}) async {
  await t.enterText(find.byType(TextField), question);
  await t.pump();
  await t.tap(find.bySemanticsLabel('Send'));
  if (settle) {
    await t.pumpAndSettle();
  } else {
    await _frames(t);
  }
}

Future<void> _open(WidgetTester t, String path) async {
  unawaited(routerOf(t).push(path));
  await t.pumpAndSettle();
}

List<ChatStreamEvent> _reply(
  String text, {
  List<Map<String, Object?>> cards = const [],
  List<String> chips = const [],
  String tool = 'get_spending_summary',
  String language = 'en',
}) => [
  ToolStatusEvent(tool),
  TokenEvent(text),
  DoneEvent(
    messageId: _ids++,
    cards: [for (final c in cards) ChatCard.fromJson(c)],
    suggestions: [for (final s in chips) Suggestion(s)],
    language: language,
  ),
];

Map<String, Object?> _flow(String flow) =>
    fixtureCards().firstWhere((c) => c['type'] == 'open_app_flow' && c['flow'] == flow);

Map<String, Object?> get _failedPayment =>
    fixtureCards().lastWhere((c) => c['type'] == 'transactions_preview');

/// One question and its scripted answer, as a whole chat screen.
class _Scene {
  const _Scene(this.name, this.question, this.reply);
  final String name;
  final String question;
  final List<ChatStreamEvent> reply;
}

List<_Scene> _scenes() => [
  _Scene(
    'screens/05_chat_spending',
    'Where did my money go last month?',
    _reply(
      'You spent **Rs. 35,097.56** in October, 5.9% less than in September. Groceries and '
      'food took the biggest share; the chart shows every category.',
      cards: [fixtureCard('spending_summary'), fixtureCard('category_breakdown')],
      chips: ['This month vs last', 'Set a food budget', 'Top merchants'],
    ),
  ),
  _Scene(
    'screens/06_chat_budget_confirm',
    'Set a food budget of Rs. 6,000',
    _reply(
      'Your **Food & Dining** budget would be **Rs. 6,000** a month; you have spent '
      'Rs. 1,270 of it so far in November.\n\nNext: tap **Confirm** to save it.',
      cards: [fixtureCard('confirm_action')],
      chips: ['My budgets', 'Where did my money go?'],
      tool: 'upsert_budget',
    ),
  ),
  _Scene(
    'screens/07_chat_budgets',
    'How are my budgets doing?',
    _reply(
      'You have used **20.7%** of your Rs. 30,000 budget for November: Rs. 6,213.80 so far. '
      'Every budget is on track.',
      cards: [fixtureCard('budget_progress')],
      chips: ['Set a food budget', 'This month vs last'],
      tool: 'get_budgets',
    ),
  ),
  _Scene(
    'screens/08_chat_bills_pay',
    'Which bills are due?',
    _reply(
      '**Ncell** Rs. 499 is due tomorrow, 10 Nov, and **Nepal Electricity Authority** '
      'about Rs. 1,140.67 on 14 Nov.\n\nNext: tap **Pay electricity bill**; you finish in '
      'Khalti with your MPIN.',
      cards: [fixtureCard('bills_list'), _flow('bill_payment')],
      chips: ['Set up Autopay', 'My balance at month end'],
      tool: 'get_recurring_payments',
    ),
  ),
  _Scene(
    'screens/09_chat_goals',
    'How are my savings goals?',
    _reply(
      '**New laptop**: Rs. 18,000 of Rs. 1,20,000 saved (15%). To reach it by 1 Sep 2027 '
      'you need **Rs. 10,200 a month**. **Emergency fund**: Rs. 8,500 of Rs. 50,000 (17%), '
      'Rs. 3,459 a month.',
      cards: [fixtureCard('goal_progress')],
      chips: ['Automate with Smart Deposit', 'Where can I save?'],
      tool: 'get_goals',
    ),
  ),
  _Scene(
    'screens/10_chat_failed_payment',
    'My Nepal Telecom top-up failed but money was deducted',
    _reply(
      '**Failed** · Rs. 500 · Nepal Telecom · 5 Nov 2026\n\nA failed payment is refunded '
      'within 24 hours where a refund applies. That time has passed, so the next step is '
      'Khalti support with this payment attached.\n\nNext: tap **Contact Khalti support**.'
      '\n\n$_support',
      cards: [_failedPayment, _flow('support')],
      chips: ["What's the refund time?"],
      tool: 'get_transaction_status',
    ),
  ),
  _Scene(
    'screens/11_chat_scam_warning',
    'Someone from Khalti called and asked for my OTP. I gave it.',
    _reply(
      '**This is likely a scam. Khalti never asks for your OTP or MPIN.**\n\nBlock your '
      'wallet now so nobody can use it, then report it to Khalti support.\n\nNext: tap '
      '**Block my wallet**.\n\n$_support',
      cards: [_flow('block_wallet')],
      chips: ['How do I report fraud?'],
      tool: 'search_help_articles',
    ),
  ),
  _Scene(
    'screens/12_chat_split_bill',
    'Split Rs. 1,000 dinner between me, Sita and Ram',
    _reply(
      '**Rs. 1,000** split 3 ways: Sita Rs. 333.33, Ram Rs. 333.33 and you Rs. 333.34.\n\n'
      'Next: tap **Split the bill** to send the requests in Khalti.',
      cards: [_flow('request_money')],
      chips: ['My spending on food'],
      tool: 'open_app_flow',
    ),
  ),
  _Scene(
    'screens/13_chat_load_money',
    'Load Rs. 5,000 from my bank',
    _reply(
      'You can load **Rs. 5,000** from your bank; it is within today\'s limit.\n\nNext: tap '
      '**Load money from bank** and confirm in Khalti with your MPIN.',
      cards: [_flow('load_money')],
      chips: ['How much more can I load today?'],
      tool: 'open_app_flow',
    ),
  ),
  _Scene(
    'screens/14_chat_inbox',
    'Do I have any unread messages?',
    _reply(
      '**Yes, 2 unread.**\n- **Money request**: Hari Gurung asked you for Rs. 800 (momo '
      'dinner) · 8 Nov 2026, 9:55 AM\n- **Money received**: Rs. 2,500 from Ram Thapa · '
      '8 Nov 2026, 7:15 AM',
      chips: ['Pay Hari Rs. 800', 'My balance'],
      tool: 'get_inbox_messages',
    ),
  ),
  _Scene(
    'screens/15_chat_nepali',
    'खानाको बजेट ६००० राख र बिजुलीको बिल तिर',
    _reply(
      'खानाको मासिक बजेट रु. 6,000 राख्न तलको Confirm थिच्नुहोस्। बिजुलीको बिल तिर्न Khalti '
      'को बिल भुक्तानी खुल्छ।',
      cards: [fixtureCard('confirm_action'), _flow('bill_payment')],
      chips: ['मेरो बजेट', 'यो महिनाको खर्च'],
      tool: 'upsert_budget',
      language: 'ne',
    ),
  ),
  _Scene(
    'screens/16_chat_romanized',
    'yo mahina khana ma kati kharcha bhayo?',
    _reply(
      'Yo mahina khana ma **Rs. 1,270** kharcha bhayo, gaya mahina bhanda kam. Sabai bhanda '
      'dherai Sasto Mitho Khaja Ghar ma gayo.',
      chips: ['Yo mahina ra gaya mahina', 'Khana ko budget rakha'],
      language: 'rom',
    ),
  ),
];

void main() {
  setUpAll(() async {
    autoUpdateGoldenFiles = true; // write the images
    await loadAppFonts();
  });

  // --- the chat, step by step ------------------------------------------------------------
  testWidgets('chat start screen', (t) async {
    await _pump(t);
    await _shot('screens/01_chat_start');
  });

  testWidgets('typing a question', (t) async {
    await _pump(t);
    await t.enterText(find.byType(TextField), 'Where did my money go last month?');
    await _frames(t, 4);
    await _shot('screens/02_chat_typing');
  });

  testWidgets('thinking (a tool is running)', (t) async {
    final chat = FakeChatRepository([
      [const ToolStatusEvent('get_spending_summary')],
    ])..holdOpen = Completer<void>();
    await _pump(t, chat: chat);
    await _ask(t, 'Where did my money go last month?', settle: false);
    await _shot('screens/03_chat_thinking');
    chat.holdOpen!.complete();
    await t.pumpAndSettle();
  });

  testWidgets('answer streaming in', (t) async {
    final chat = FakeChatRepository([
      [
        const ToolStatusEvent('get_spending_summary'),
        const TokenEvent('You spent **Rs. 35,097.56** in October, 5.9% less than in '),
      ],
    ])..holdOpen = Completer<void>();
    await _pump(t, chat: chat);
    await _ask(t, 'Where did my money go last month?', settle: false);
    await _shot('screens/04_chat_streaming');
    chat.holdOpen!.complete();
    await t.pumpAndSettle();
  });

  for (final scene in _scenes()) {
    testWidgets(scene.name, (t) async {
      await _pump(t, chat: FakeChatRepository([scene.reply]));
      await _ask(t, scene.question);
      await _shot(scene.name);
    });
  }

  testWidgets('chat menu (behind the mascot)', (t) async {
    await _pump(t);
    await openChatMenu(t);
    await _shot('screens/17_chat_menu');
  });

  testWidgets('a receipt photo sent', (t) async {
    final files = FakeFileSource()..photos.add([PickedFile('receipt.png', samplePhoto)]);
    final chat = FakeChatRepository([
      _reply(
        'You bought from **Himalayan Fresh Mart** on 13 Nov:\n- Rice Rs. 1,150\n- Milk '
        'Rs. 190\n- Eggs Rs. 480\n- Tea Rs. 325\nTotal: **Rs. 2,145**.',
        chips: ['How does this compare with my spending?'],
        tool: 'read_attachment',
      ),
    ]);
    await _pump(t, chat: chat, files: files);
    await t.tap(find.byTooltip('Add files and photos'));
    await t.pumpAndSettle();
    await t.tap(find.text('Photo'));
    await t.pumpAndSettle();
    await t.runAsync(
      () => precacheImage(MemoryImage(samplePhoto), t.element(find.byType(Navigator).first)),
    );
    await t.pumpAndSettle();
    await _ask(t, 'What did I buy?');
    await _shot('screens/18_chat_receipt');
  });

  testWidgets('a whole conversation (tall)', (t) async {
    final scenes = _scenes();
    final picked = [scenes[0], scenes[1], scenes[3], scenes[4]];
    await _pump(t, chat: FakeChatRepository([for (final s in picked) s.reply]), size: const Size(393, 3330));
    for (final s in picked) {
      await _ask(t, s.question);
    }
    await _shot('tall/chat_conversation');
  });

  // --- the other screens ------------------------------------------------------------------
  for (final (name, path) in [
    ('19_insights', OkayRoutes.insights),
    ('20_transactions', OkayRoutes.transactions),
    ('21_budgets', OkayRoutes.budgets),
    ('22_goals', OkayRoutes.goals),
    ('23_bills', OkayRoutes.bills),
    ('24_alerts', OkayRoutes.alerts),
    ('25_settings', OkayRoutes.settings),
  ]) {
    testWidgets(name, (t) async {
      await _pump(t);
      await _open(t, path);
      await _shot('screens/$name');
    });
    testWidgets('$name (tall)', (t) async {
      await _pump(t, size: _tall);
      await _open(t, path);
      await _shot('tall/${name.substring(3)}');
    });
  }

  testWidgets('budget sheet', (t) async {
    await _pump(t);
    await _open(t, OkayRoutes.budgets);
    await t.tap(find.text('Groceries'));
    await t.pumpAndSettle();
    await _shot('screens/26_budget_sheet');
  });

  testWidgets('transaction sheet', (t) async {
    await _pump(t);
    await _open(t, OkayRoutes.transactions);
    await t.tap(find.textContaining('Sasto Mitho Khaja Ghar').first);
    await t.pumpAndSettle();
    await _shot('screens/27_transaction_sheet');
  });

  testWidgets('insights with amounts hidden', (t) async {
    await _pump(t);
    await hideAmounts(t);
    await _open(t, OkayRoutes.insights);
    await _shot('screens/28_insights_hidden');
  });

  // --- parts, on a transparent background --------------------------------------------------
  /// [child] at its own height (as in the chat's list), [width] points wide (null: its own
  /// width), saved at 4x with a transparent background around it.
  Future<void> part(WidgetTester t, String name, Widget child, {double? width = 361}) async {
    t.view.physicalSize = const Size(393, 2600) * _partScale;
    t.view.devicePixelRatio = _partScale;
    addTearDown(t.view.reset);
    const key = ValueKey('part');
    final nav = GlobalKey<NavigatorState>();
    await t.pumpWidget(
      ProviderScope(
        overrides: [
          hostAppBridgeProvider.overrideWithValue(MockHostAppBridge(nav)),
          clockProvider.overrideWithValue(() => fixtureNow),
        ],
        child: MaterialApp(
          navigatorKey: nav,
          debugShowCheckedModeBanner: false,
          theme: buildOkayTheme(),
          home: Material(
            type: MaterialType.transparency,
            child: SingleChildScrollView(
              child: Align(
                alignment: Alignment.topLeft,
                child: RepaintBoundary(
                  key: key,
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: width == null ? child : SizedBox(width: width, child: child),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
    await t.pumpAndSettle();
    final boundary = t.renderObject<RenderRepaintBoundary>(find.byKey(key));
    await t.runAsync(() async {
      final image = await boundary.toImage(pixelRatio: _partScale);
      final png = await image.toByteData(format: ui.ImageByteFormat.png);
      final file = File('../motion-reference/parts/$name.png');
      await file.parent.create(recursive: true);
      await file.writeAsBytes(png!.buffer.asUint8List());
      image.dispose();
    });
  }

  final seen = <String>{};
  for (final card in fixtureCards()) {
    final name = [card['type'], if (card['flow'] case final String flow) flow].join('_');
    if (!seen.add(name)) continue;
    testWidgets('part: $name', (t) async {
      await part(
        t,
        'card_$name',
        ChatCardView(card: ChatCard.fromJson(card), messageIndex: 0, cardIndex: 0),
      );
    });
  }

  testWidgets('part: Ask me button', (t) async {
    await part(t, 'ask_me_button', const AskMeButton(), width: null);
  });
}
