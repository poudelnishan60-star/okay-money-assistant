import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/ai_assistant.dart';

import 'test_harness.dart';

/// Every chat card, with the bundled fonts, on small phones and with large system text:
/// nothing may overflow (cheap Android phones are often 360 px wide; some users run 130%).
Future<void> _load(String family, List<String> files) async {
  final loader = FontLoader(family);
  for (final f in files) {
    loader.addFont(Future.value(ByteData.view(File(f).readAsBytesSync().buffer)));
  }
  await loader.load();
}

void main() {
  setUpAll(() async {
    await _load('DM Sans', [
      for (final w in ['Regular', 'Medium', 'SemiBold', 'Bold']) 'assets/fonts/DMSans-$w.ttf',
    ]);
    await _load('Noto Sans Devanagari', [
      'assets/fonts/NotoSansDevanagari-Regular.ttf',
      'assets/fonts/NotoSansDevanagari-SemiBold.ttf',
    ]);
  });

  for (final (width, scale) in [(320.0, 1.0), (360.0, 1.3), (390.0, 1.3)]) {
    testWidgets('no overflow at $width px with text x$scale', (t) async {
      useSize(t, Size(width, 4000));
      t.platformDispatcher.textScaleFactorTestValue = scale;
      addTearDown(t.platformDispatcher.clearTextScaleFactorTestValue);
      final chat = FakeChatRepository([
        answer(
          'खानाको बजेट रु. ६,००० — Tap Confirm to save it.',
          cardTypes: [
            'spending_summary',
            'category_breakdown',
            'budget_progress',
            'bills_list',
            'goal_progress',
            'transactions_preview',
            'confirm_action',
            'open_app_flow',
          ],
        ),
      ]);
      await t.pumpWidget(demoApp(chat: chat).app);
      await t.pumpAndSettle();
      expect(t.takeException(), isNull, reason: 'empty chat');
      await t.tap(find.text('Budgets'));
      await t.pumpAndSettle();
      expect(t.takeException(), isNull, reason: 'answer with every card');
    });

    testWidgets('files fit at $width px with text x$scale', (t) async {
      useSize(t, Size(width, 1600));
      t.platformDispatcher.textScaleFactorTestValue = scale;
      addTearDown(t.platformDispatcher.clearTextScaleFactorTestValue);
      final files = FakeFileSource()
        ..documents.add([
          PickedFile('a-very-long-statement-name-from-the-bank.xlsx', samplePhoto),
          PickedFile('receipt.png', samplePhoto),
          PickedFile('nea-bill-november.pdf', samplePhoto),
        ]);
      final chat = FakeChatRepository([answer('Read them.')]);
      await t.pumpWidget(demoApp(chat: chat, files: files).app);
      await t.pumpAndSettle();
      await t.tap(find.byTooltip('Add files and photos'));
      await t.pumpAndSettle();
      expect(t.takeException(), isNull, reason: 'add sheet');
      await t.tap(find.text('Document'));
      await t.pumpAndSettle();
      expect(t.takeException(), isNull, reason: 'three files waiting');
      await t.tap(find.bySemanticsLabel('Send'));
      await t.pumpAndSettle();
      expect(t.takeException(), isNull, reason: 'sent files in the bubble');
    });
  }

  for (final (width, scale) in [(320.0, 1.0), (360.0, 1.3), (390.0, 1.3)]) {
    testWidgets('screens fit at $width px with text x$scale', (t) async {
      useSize(t, Size(width, 4000));
      t.platformDispatcher.textScaleFactorTestValue = scale;
      addTearDown(t.platformDispatcher.clearTextScaleFactorTestValue);
      await t.pumpWidget(demoApp().app);
      await t.pumpAndSettle();
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
        expect(t.takeException(), isNull, reason: path);
        if (path == OkayRoutes.budgets || path == OkayRoutes.goals) {
          await t.tap(find.byIcon(Icons.add_rounded).first);
          await t.pumpAndSettle();
          expect(t.takeException(), isNull, reason: '$path sheet');
          Navigator.of(t.element(find.text('Save'))).pop();
          await t.pumpAndSettle();
        }
        router.pop();
        await t.pumpAndSettle();
      }
    });
  }
}
