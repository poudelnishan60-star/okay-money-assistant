import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/ai_assistant.dart';

import 'test_harness.dart';

void main() {
  testWidgets('the site opens straight into the O-Kay chat, with no host screens', (t) async {
    usePhoneSize(t);
    await t.pumpWidget(demoApp().app);
    await t.pumpAndSettle();
    expect(find.text('Start Chatting with O-Kay'), findsOneWidget);
    expect(find.byType(BackButton), findsNothing); // the chat is the front page
    for (final gone in ['Khalti Balance', 'Financial Services', 'Cards', 'Menu', 'Ask me']) {
      expect(find.text(gone), findsNothing);
    }
  });

  testWidgets('the chat header leads to the dashboard, alerts and settings', (t) async {
    usePhoneSize(t);
    await t.pumpWidget(demoApp().app);
    await t.pumpAndSettle();

    await t.tap(find.byTooltip('Money Insights'));
    await t.pumpAndSettle();
    expect(find.text('Spent so far'), findsOneWidget);
    await t.tap(find.byType(BackButton));
    await t.pumpAndSettle();
    expect(find.text('Start Chatting with O-Kay'), findsOneWidget);

    await t.tap(find.byTooltip('Alerts, 3 unread'));
    await t.pumpAndSettle();
    expect(find.text('Ncell is due tomorrow'), findsOneWidget);
    await t.tap(find.byType(BackButton));
    await t.pumpAndSettle();

    await t.tap(find.byTooltip('More'));
    await t.pumpAndSettle();
    // Nothing to clear yet.
    expect(find.byWidgetPredicate((w) => w is PopupMenuItem && !w.enabled), findsOneWidget);
    await t.tap(find.text('Assistant settings'));
    await t.pumpAndSettle();
    expect(find.text('Language'), findsOneWidget);
    await t.tap(find.byType(BackButton));
    await t.pumpAndSettle();
    expect(find.text('Start Chatting with O-Kay'), findsOneWidget);
  });

  testWidgets('flag off: nothing opens and the routes bounce to the switched-off page', (t) async {
    usePhoneSize(t);
    await t.pumpWidget(demoApp(enabled: false).app);
    await t.pumpAndSettle();
    expect(find.text('O-Kay is switched off'), findsOneWidget);
    expect(find.text('Start Chatting with O-Kay'), findsNothing);

    for (final path in [OkayRoutes.chat, OkayRoutes.insights, OkayRoutes.settings]) {
      routerOf(t).go(path);
      await t.pumpAndSettle();
      expect(find.text('O-Kay is switched off'), findsOneWidget, reason: path);
    }
  });

  testWidgets('the browser tab is named after the screen on top, also after going back', (t) async {
    final titles = <String>[];
    t.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, (
      call,
    ) async {
      if (call.method == 'SystemChrome.setApplicationSwitcherDescription') {
        titles.add((call.arguments as Map<Object?, Object?>)['label']! as String);
      }
      return null;
    });
    addTearDown(
      () =>
          t.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, null),
    );
    usePhoneSize(t);
    await t.pumpWidget(demoApp().app);
    await t.pumpAndSettle();
    expect(titles.last, 'Chat · O-Kay');
    await t.tap(find.byTooltip('Money Insights'));
    await t.pumpAndSettle();
    expect(titles.last, 'Money Insights · O-Kay');
    await t.tap(find.byType(BackButton));
    await t.pumpAndSettle();
    expect(titles.last, 'Chat · O-Kay');
  });

  testWidgets('/assistant redirects to insights', (t) async {
    usePhoneSize(t);
    await t.pumpWidget(demoApp().app);
    await t.pumpAndSettle();
    routerOf(t).go(OkayRoutes.root);
    await t.pumpAndSettle();
    expect(find.text('Spent so far'), findsOneWidget);
  });

  testWidgets('UI kit renders every component; the Ask me entry point opens the chat', (t) async {
    usePhoneSize(t);
    await t.pumpWidget(demoApp().app);
    await t.pumpAndSettle();
    routerOf(t).go(OkayRoutes.uiKit);
    await t.pumpAndSettle();
    expect(find.text('Assistant UI kit'), findsOneWidget);
    await t.dragUntilVisible(
      find.text('States'),
      find.byType(Scrollable).first,
      const Offset(0, -400),
    );
    await t.pumpAndSettle();
    expect(t.takeException(), isNull);

    // For the Khalti app's Home: the floating button that opens the chat.
    await t.ensureVisible(find.text('Ask me'));
    await t.pumpAndSettle();
    await t.tap(find.text('Ask me'));
    await t.pumpAndSettle();
    expect(find.text('Start Chatting with O-Kay'), findsOneWidget);
    expect(find.byType(BackButton), findsOneWidget);
  });
}
