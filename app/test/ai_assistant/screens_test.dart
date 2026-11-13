import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/ai_assistant.dart';

import 'test_harness.dart';

/// Opens an assistant screen in the demo host, phone-sized, against the fake backend.
Future<FakeApi> open(WidgetTester t, String path, {FakeApi? api, FakeChatRepository? chat}) async {
  useSize(t, const Size(390, 1600));
  final demo = demoApp(api: api, chat: chat);
  await t.pumpWidget(demo.app);
  await t.pumpAndSettle();
  unawaited(routerOf(t).push(path));
  await t.pumpAndSettle();
  return demo.api;
}

/// A finger pulling the list down slowly, as a person does to reload.
Future<void> pullDown(WidgetTester t, Finder from) async {
  final g = await t.startGesture(t.getCenter(from));
  for (var i = 0; i < 20; i++) {
    await g.moveBy(const Offset(0, 20));
    await t.pump(const Duration(milliseconds: 16));
  }
  await g.up();
  await t.pumpAndSettle();
}

Future<void> scrollTo(WidgetTester t, Finder f) async {
  await t.scrollUntilVisible(f, 300, scrollable: find.byType(Scrollable).last);
  await t.pumpAndSettle();
}

void main() {
  alertsAndPrivacy();

  group('Insights dashboard', () {
    testWidgets('shows total, change, insights, forecast, categories, days, merchants', (t) async {
      await open(t, OkayRoutes.insights);
      expect(find.text('Nov 2026'), findsOneWidget);
      expect(find.text('Spent so far'), findsOneWidget);
      expect(find.text('Rs. 6,213.80'), findsWidgets);
      expect(find.text('64.7% less than the same days of Oct 2026'), findsOneWidget);
      expect(find.textContaining('Education is your biggest category'), findsOneWidget);
      expect(find.textContaining('Balance on 30 Nov'), findsOneWidget);
      // projected month-end balance (also the lowest point: they coincide on 30 Nov)
      expect(find.text('Rs. 8,286'), findsWidgets);
      await scrollTo(t, find.text('Top merchants'));
      expect(find.text('By category'), findsOneWidget);
      expect(find.text('Day by day'), findsOneWidget);
      expect(find.text('Sikshya Language Institute'), findsWidgets);
    });

    testWidgets('previous month: unusual spending flagged, no forecast', (t) async {
      final api = await open(t, OkayRoutes.insights);
      await t.tap(find.byTooltip('Previous month'));
      await t.pumpAndSettle();
      expect(api.requests.last, contains('/insights/dashboard?month=2026-10'));
      expect(find.text('Oct 2026'), findsOneWidget);
      expect(find.textContaining('Shopping is at 6.9x its usual level'), findsOneWidget);
      expect(find.textContaining('(forecast)'), findsNothing);
    });

    testWidgets('a category row opens its transactions', (t) async {
      final api = await open(t, OkayRoutes.insights);
      await scrollTo(t, find.text('Education'));
      await t.tap(find.text('Education').last);
      await t.pumpAndSettle();
      expect(find.text('Transactions'), findsOneWidget);
      final req = api.requests.lastWhere((r) => r.startsWith('GET /transactions'));
      expect(Uri.decodeFull(req), contains('category=Education'));
      expect(req, contains('spending_only=true'));
      expect(find.byType(InputChip), findsOneWidget); // the filter chip, clearable
    });
  });

  group('Transactions', () {
    testWidgets('grouped by day with closing balances; chips and paging', (t) async {
      final api = await open(t, OkayRoutes.transactions);
      expect(api.requests.last, contains('period=30d'));
      expect(find.text('Closing Balance'), findsWidgets);
      expect(find.textContaining('154 transactions'), findsOneWidget);
      await t.tap(find.text('7 days'));
      await t.pumpAndSettle();
      expect(api.requests.last, contains('period=7d'));
      await t.tap(find.text('30 days'));
      await t.pumpAndSettle();
      await scrollTo(t, find.text('Load more'));
      await t.tap(find.text('Load more'));
      await t.pumpAndSettle();
      expect(api.requests.last, contains('offset=50'));
    });

    testWidgets('detail sheet: change category for all from a merchant', (t) async {
      final api = await open(t, OkayRoutes.transactions);
      await t.tap(find.textContaining('Sasto Mitho Khaja Ghar').first);
      await t.pumpAndSettle();
      expect(find.text('Merchant'), findsOneWidget);
      expect(find.text('Category'), findsOneWidget);
      await t.tap(find.byType(DropdownButtonFormField<String>));
      await t.pumpAndSettle();
      await t.tap(find.text('Groceries').last);
      await t.pumpAndSettle();
      await t.tap(find.textContaining('Apply to all from'));
      await t.pumpAndSettle();
      await t.tap(find.text('Save'));
      await t.pumpAndSettle();
      expect(api.requests.where((r) => r.startsWith('PATCH /transactions/')), hasLength(1));
      expect(api.bodies.last, {
        'category': 'Groceries',
        'subcategory': null,
        'apply_to_merchant': true,
      });
      expect(find.textContaining('Updated'), findsOneWidget); // snackbar
    });

    testWidgets("a person's note is shown as plain text", (t) async {
      await open(t, OkayRoutes.transactions);
      await scrollTo(t, find.textContaining('Bikash Gurung').first);
      await t.tap(find.textContaining('Bikash Gurung').first);
      await t.pumpAndSettle();
      expect(find.text('Note'), findsOneWidget);
    });
  });

  group('Budgets', () {
    testWidgets('list with words, not just colour', (t) async {
      await open(t, OkayRoutes.budgets);
      expect(find.text('Overall'), findsOneWidget);
      expect(find.text('Groceries'), findsOneWidget);
      expect(find.textContaining('On track'), findsWidgets);
      expect(find.textContaining('a day for'), findsWidgets);
    });

    testWidgets('pull down to reload', (t) async {
      final api = await open(t, OkayRoutes.budgets);
      int loads() => api.requests.where((r) => r == 'GET /budgets').length;
      final before = loads();
      await pullDown(t, find.text('Overall'));
      await t.pumpAndSettle();
      expect(loads(), before + 1);
    });

    testWidgets('create a food budget from the sheet', (t) async {
      final api = await open(t, OkayRoutes.budgets);
      await t.tap(find.byTooltip('New budget'));
      await t.pumpAndSettle();
      await t.tap(find.byType(DropdownButtonFormField<String>));
      await t.pumpAndSettle();
      await t.tap(find.text('Food & Dining').last);
      await t.pumpAndSettle();
      await t.enterText(find.byType(TextField), '६,०००'); // Devanagari digits work too
      await t.tap(find.text('Save'));
      await t.pumpAndSettle();
      expect(api.bodies.last, {
        'category': 'Food & Dining',
        'limit_paisa': 600000,
        'calendar': 'AD',
      });
      expect(find.text('Food & Dining'), findsOneWidget);
    });

    testWidgets('validation and edit/delete', (t) async {
      final api = await open(t, OkayRoutes.budgets);
      await t.tap(find.text('Groceries'));
      await t.pumpAndSettle();
      await t.enterText(find.byType(TextField), 'abc');
      await t.tap(find.text('Save'));
      await t.pumpAndSettle();
      expect(find.text('Enter an amount above 0.'), findsOneWidget);
      await t.enterText(find.byType(TextField), '10000');
      await t.tap(find.text('Nepali (BS) month'));
      await t.tap(find.text('Save'));
      await t.pumpAndSettle();
      expect(api.requests.last, 'GET /budgets');
      expect(api.bodies.last, {'limit_paisa': 1000000, 'calendar': 'BS'});
      await t.tap(find.text('Groceries'));
      await t.pumpAndSettle();
      await t.tap(find.text('Delete this budget'));
      await t.pumpAndSettle();
      expect(find.text('Groceries'), findsNothing);
    });
  });

  group('Goals', () {
    testWidgets('ring, needs per month, Automate with Smart Deposit', (t) async {
      await open(t, OkayRoutes.goals);
      expect(find.text('New laptop'), findsOneWidget);
      expect(find.text('/month for 10 months'), findsOneWidget);
      expect(find.text('Rs. 10,200'), findsOneWidget);
      expect(find.text('Smart Deposit - New laptop'), findsOneWidget); // existing plan
      await t.tap(find.text('Automate with Smart Deposit').first);
      await t.pumpAndSettle();
      expect(find.text('Would open Smart Deposit'), findsOneWidget);
      expect(find.text('New laptop'), findsWidgets); // pre-filled goal name in the sheet
    });

    testWidgets('new goal sheet validates', (t) async {
      final api = await open(t, OkayRoutes.goals);
      await t.tap(find.byTooltip('New goal'));
      await t.pumpAndSettle();
      await t.tap(find.text('Save'));
      await t.pumpAndSettle();
      expect(find.text('Give the goal a name.'), findsOneWidget);
      await t.enterText(find.byType(TextField).at(0), 'Pokhara trip');
      await t.enterText(find.byType(TextField).at(1), '25,000');
      await t.tap(find.text('Save'));
      await t.pumpAndSettle();
      expect(find.text('Pick a deadline.'), findsOneWidget);
      expect(api.requests.where((r) => r.startsWith('POST')), isEmpty);
    });
  });

  group('Bills', () {
    testWidgets('due soon, pay, autopay, dismiss and undo', (t) async {
      final demoApi = FakeApi();
      final api = await open(t, OkayRoutes.bills, api: demoApi);
      expect(find.text('Ncell'), findsOneWidget);
      expect(find.textContaining('Due in 1 day'), findsOneWidget);
      await t.tap(find.text('Pay now').first);
      await t.pumpAndSettle();
      expect(find.text('Would open Bill Payment (data_pack)'), findsOneWidget);
      await t.tap(find.text('OK'));
      await t.pumpAndSettle();
      await t.tap(find.text('Dismiss').first);
      await t.pumpAndSettle();
      expect(jsonEncode(api.bodies.last), '{"status":"dismissed"}');
      await scrollTo(t, find.text('Dismissed (1)'));
      await t.tap(find.text('Dismissed (1)'));
      await t.pumpAndSettle();
      await scrollTo(t, find.text('Undo'));
      await t.tap(find.text('Undo'));
      await t.pumpAndSettle();
      expect(jsonEncode(api.bodies.last), '{"status":"detected"}');
    });
  });

  group('Settings', () {
    testWidgets('language and calendar are saved and used', (t) async {
      final chat = FakeChatRepository([answer('नमस्ते')]);
      final api = await open(t, OkayRoutes.settings, chat: chat);
      expect(find.text('English'), findsOneWidget);
      await t.tap(find.text('नेपाली'));
      await t.pumpAndSettle();
      expect(api.settings['language'], 'ne');
      await t.tap(find.text('BS (Nepali)'));
      await t.pumpAndSettle();
      expect(api.settings['calendar'], 'BS');

      // The chat now asks in Nepali, and dates show in BS.
      unawaited(GoRouter.of(t.element(find.text('Assistant settings'))).push(OkayRoutes.chat));
      await t.pumpAndSettle();
      await t.tap(find.text('Budgets'));
      await t.pumpAndSettle();
      expect(chat.sent.single.$2, 'ne');
    });

    testWidgets('Hide amounts masks them until one is tapped', (t) async {
      await open(t, OkayRoutes.settings);
      await scrollTo(t, find.text('Hide amounts'));
      await t.tap(find.text('Hide amounts'));
      await t.pumpAndSettle();
      expect(find.text('Warn me if my balance may drop below Rs. ••••'), findsOneWidget);
      unawaited(routerOf(t).push(OkayRoutes.budgets));
      await t.pumpAndSettle();
      expect(find.text('Rs. 30,000'), findsNothing);
      await t.tap(find.text('Rs. ••••').first);
      await t.pumpAndSettle();
      expect(find.text('Rs. 30,000'), findsOneWidget); // one tap shows them all again
    });

    testWidgets('alerts toggles, data explainer, clear chat', (t) async {
      final chat = FakeChatRepository();
      final api = await open(t, OkayRoutes.settings, chat: chat);
      await t.tap(find.text('Unusual spending'));
      await t.pumpAndSettle();
      expect((api.settings['alerts']! as Map)['unusual'], isFalse);
      await scrollTo(t, find.text('Clear chat history'));
      expect(find.text('How O-Kay uses your data'), findsOneWidget);
      await t.tap(find.text('Clear chat history'));
      await t.pumpAndSettle();
      await t.tap(find.text('Clear'));
      await t.pumpAndSettle();
      expect(chat.cleared, isTrue);
    });
  });
}

void alertsAndPrivacy() {
  group('Alerts', () {
    testWidgets('bell badge, new and earlier, open one, mark all read', (t) async {
      final api = await open(t, OkayRoutes.insights);
      expect(find.byTooltip('Alerts, 3 unread'), findsOneWidget);
      await t.tap(find.byTooltip('Alerts, 3 unread'));
      await t.pumpAndSettle();
      expect(find.text('New'), findsOneWidget);
      expect(find.text('Earlier'), findsNothing);
      expect(find.text('Your week: Rs. 5,872.80 spent'), findsOneWidget);
      expect(find.text('Shopping budget at 80%'), findsOneWidget);

      await t.tap(find.text('Ncell is due tomorrow'));
      await t.pumpAndSettle();
      expect(find.text('Bills & subscriptions'), findsOneWidget);
      expect(api.bodies.last, {
        'ids': [2],
      });
      GoRouter.of(t.element(find.text('Bills & subscriptions'))).pop();
      await t.pumpAndSettle();
      expect(find.text('Earlier'), findsOneWidget);

      await t.tap(find.text('Mark all read'));
      await t.pumpAndSettle();
      expect(api.bodies.last, {'ids': null});
      expect(find.text('New'), findsNothing);
      expect(find.text('Mark all read'), findsNothing);
    });

    testWidgets('an unusual-spending alert opens the filtered transactions', (t) async {
      final api = FakeApi();
      api.alerts.insert(0, {
        'id': 9,
        'kind': 'unusual',
        'title': 'Unusual spending on Shopping',
        'body': 'Rs. 8,280 so far in Oct 2026: 6.9x your usual Rs. 1,200 for this many days.',
        'day': '2026-10-31',
        'read': false,
        'link': {
          'screen': 'transactions',
          'params': {
            'category': 'Shopping',
            'start': '2026-10-01',
            'end': '2026-10-31',
            'spending_only': 'true',
          },
        },
        'data': <String, Object?>{},
      });
      await open(t, OkayRoutes.alerts, api: api);
      await t.tap(find.text('Unusual spending on Shopping'));
      await t.pumpAndSettle();
      expect(find.text('Transactions'), findsOneWidget);
      final req = Uri.decodeFull(api.requests.lastWhere((r) => r.startsWith('GET /transactions')));
      expect(req, contains('category=Shopping'));
      expect(req, contains('start=2026-10-01'));
      expect(find.byType(InputChip), findsOneWidget); // the filter, clearable
    });

    testWidgets('empty inbox explains what alerts there are', (t) async {
      final api = FakeApi()..alerts.clear();
      await open(t, OkayRoutes.alerts, api: api);
      expect(find.text('No alerts yet'), findsOneWidget);
      await t.tap(find.text('Alert settings'));
      await t.pumpAndSettle();
      expect(find.text('Assistant settings'), findsOneWidget);
    });

    testWidgets("the chat's bell shows the alerts", (t) async {
      useSize(t, const Size(390, 1600));
      await t.pumpWidget(demoApp().app);
      await t.pumpAndSettle();
      await t.tap(find.byTooltip('Alerts, 3 unread'));
      await t.pumpAndSettle();
      expect(find.text('Alerts'), findsOneWidget);
    });

    testWidgets('settings: low-balance warning line', (t) async {
      final api = await open(t, OkayRoutes.settings);
      await scrollTo(t, find.text('Low-balance warning'));
      expect(find.text('Warn me if my balance may drop below Rs. 1,000'), findsOneWidget);
      await t.tap(find.text('Low-balance warning'));
      await t.pumpAndSettle();
      await t.enterText(find.byType(TextField), '0');
      await t.tap(find.text('Save'));
      await t.pumpAndSettle();
      expect(find.text('Enter an amount above 0.'), findsOneWidget);
      await t.enterText(find.byType(TextField), '2,500');
      await t.tap(find.text('Save'));
      await t.pumpAndSettle();
      expect(api.settings['low_balance_threshold_paisa'], 250000);
      expect(find.text('Warn me if my balance may drop below Rs. 2,500'), findsOneWidget);
    });
  });
}
