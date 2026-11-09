import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

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
      expect(t.takeException(), isNull, reason: 'home');
      await t.tap(find.text('Ask me'));
      await t.pumpAndSettle();
      expect(t.takeException(), isNull, reason: 'empty chat');
      await t.tap(find.text('Budgets'));
      await t.pumpAndSettle();
      expect(t.takeException(), isNull, reason: 'answer with every card');
    });
  }
}
