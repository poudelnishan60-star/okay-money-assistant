import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/ai_assistant.dart';

import 'test_harness.dart';

void main() {
  testWidgets('Home shows the entry points when the flag is on', (tester) async {
    usePhoneSize(tester);
    await tester.pumpWidget(demoApp().app);
    await tester.pumpAndSettle();
    expect(find.text('Hi, Anjali'), findsOneWidget);
    expect(find.text('Rs. 23,944.86'), findsOneWidget);
    expect(find.text('Money Insights'), findsOneWidget);
    expect(find.text('Ask me'), findsOneWidget);
  });

  testWidgets('Money Insights tile and Ask me button open the assistant', (tester) async {
    usePhoneSize(tester);
    await tester.pumpWidget(demoApp().app);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Money Insights'));
    await tester.pumpAndSettle();
    expect(find.text('Spent so far'), findsOneWidget);
    expect(find.byType(BackButton), findsOneWidget);
    await tester.tap(find.byType(BackButton));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Ask me'));
    await tester.pumpAndSettle();
    expect(find.text('Start Chatting with O-Kay'), findsOneWidget);
  });

  testWidgets('flag off: no entry points and the routes bounce to Home', (tester) async {
    usePhoneSize(tester);
    await tester.pumpWidget(demoApp(enabled: false).app);
    await tester.pumpAndSettle();
    expect(find.text('Money Insights'), findsNothing);
    expect(find.text('Ask me'), findsNothing);

    GoRouter.of(tester.element(find.text('Financial Services'))).go(OkayRoutes.chat);
    await tester.pumpAndSettle();
    expect(find.text('Start Chatting with O-Kay'), findsNothing);
    expect(find.text('Financial Services'), findsOneWidget);
  });

  testWidgets('/assistant redirects to insights', (tester) async {
    usePhoneSize(tester);
    await tester.pumpWidget(demoApp().app);
    await tester.pumpAndSettle();
    GoRouter.of(tester.element(find.text('Financial Services'))).go(OkayRoutes.root);
    await tester.pumpAndSettle();
    expect(find.text('Spent so far'), findsOneWidget);
  });

  testWidgets('bottom nav: tabs switch, active tab is pink, Scan & Pay is host-only', (
    tester,
  ) async {
    usePhoneSize(tester);
    await tester.pumpWidget(demoApp().app);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Menu'));
    await tester.pumpAndSettle();
    expect(find.text('Assistant UI kit'), findsOneWidget);
    final menuLabel = tester.widget<Text>(find.text('Menu').last);
    expect(menuLabel.style?.color, OkayColors.accentPink);

    await tester.tap(find.bySemanticsLabel('Scan and Pay'));
    await tester.pump();
    expect(find.textContaining('Scan & Pay is part of the Khalti app'), findsOneWidget);
  });

  testWidgets('Home quick action uses the bridge; balance eye masks amounts', (tester) async {
    usePhoneSize(tester);
    final demo = demoApp();
    await tester.pumpWidget(demo.app);
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Hide balance'));
    await tester.pump();
    expect(find.text('Rs. ••••'), findsOneWidget);

    await tester.tap(find.text('Electricity'));
    await tester.pumpAndSettle();
    expect(find.text('Would open Bill Payment (electricity)'), findsOneWidget);
    expect(demo.bridge.calls, ['openBillPayment:electricity']);
  });

  testWidgets('UI kit screen renders every component without overflow', (tester) async {
    usePhoneSize(tester);
    await tester.pumpWidget(demoApp().app);
    await tester.pumpAndSettle();
    GoRouter.of(tester.element(find.text('Financial Services'))).go(OkayRoutes.uiKit);
    await tester.pumpAndSettle();
    expect(find.text('Assistant UI kit'), findsOneWidget);
    await tester.dragUntilVisible(
      find.text('States'),
      find.byType(Scrollable).first,
      const Offset(0, -400),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });
}
