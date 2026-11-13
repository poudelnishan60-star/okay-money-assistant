// Golden images of the key screens, with the bundled fonts and the backend's fixture data, so
// a visual change shows up as a failing test with a diff image.
//
//   flutter test test/goldens                    # compare
//   flutter test test/goldens --update-goldens   # accept the new look (then review the PNGs)
//
// Rendered on Windows. Other systems rasterize text slightly differently, so a small difference
// is tolerated (see _TolerantComparator); a real layout change is far larger.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/ai_assistant.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/chat/chat_models.dart';

import '../ai_assistant/test_harness.dart';

class _TolerantComparator extends LocalFileComparator {
  _TolerantComparator(super.testFile);

  /// Share of pixels that may differ (anti-aliasing on another OS or Flutter version).
  static const tolerance = 0.005;

  @override
  Future<bool> compare(Uint8List imageBytes, Uri golden) async {
    final result = await GoldenFileComparator.compareLists(
      imageBytes,
      await getGoldenBytes(golden),
    );
    if (result.passed || result.diffPercent <= tolerance) {
      result.dispose();
      return true;
    }
    final error = await generateFailureOutput(result, golden, basedir);
    result.dispose();
    throw FlutterError(error);
  }
}

const _phone = Size(390, 1200);

Future<FakeApi> _pumpHost(WidgetTester t, {FakeChatRepository? chat, FakeApi? api}) async {
  t.view.physicalSize = _phone * 1.5;
  t.view.devicePixelRatio = 1.5;
  addTearDown(t.view.reset);
  final demo = demoApp(chat: chat, api: api);
  await t.pumpWidget(demo.app);
  await t.pumpAndSettle();
  return demo.api;
}

Future<void> _open(WidgetTester t, String path) async {
  unawaited(routerOf(t).push(path));
  await t.pumpAndSettle();
}

Future<void> _matches(String name) =>
    expectLater(find.byType(MaterialApp).first, matchesGoldenFile('images/$name.png'));

void main() {
  setUpAll(() async {
    await loadAppFonts();
    final base = goldenFileComparator as LocalFileComparator;
    goldenFileComparator = _TolerantComparator(base.basedir.resolve('goldens_test.dart'));
  });

  testWidgets('chat empty state', (t) async {
    await _pumpHost(t);
    await _matches('chat_empty');
  });

  testWidgets('chat answer with spending cards', (t) async {
    final chat = FakeChatRepository([
      answer(
        'You spent **Rs. 6,213.80** so far this month, 64.7% less than the same days of '
        'last month. Education was the biggest share.',
        cardTypes: ['spending_summary', 'category_breakdown'],
        suggestions: const [Suggestion('This month vs last'), Suggestion('Set a food budget')],
      ),
    ]);
    await _pumpHost(t, chat: chat);
    await t.tap(find.text('My spending'));
    await t.pumpAndSettle();
    await _matches('chat_spending');
  });

  testWidgets('chat in Nepali with confirm and pay cards', (t) async {
    final chat = FakeChatRepository([
      answer(
        'खानाको मासिक बजेट रु. 6,000 राख्न तलको Confirm थिच्नुहोस्। बिजुलीको बिल तिर्न '
        'Khalti को बिल भुक्तानी खुल्छ।',
        cardTypes: ['confirm_action', 'open_app_flow'],
        suggestions: const [Suggestion('मेरो बजेट')],
      ),
    ]);
    await _pumpHost(t, chat: chat);
    await t.enterText(find.byType(TextField), 'खानाको बजेट ६००० राख र बिजुलीको बिल तिर');
    await t.pump();
    await t.tap(find.bySemanticsLabel('Send'));
    await t.pumpAndSettle();
    await _matches('chat_nepali_actions');
  });

  for (final (name, path) in [
    ('insights', OkayRoutes.insights),
    ('transactions', OkayRoutes.transactions),
    ('budgets', OkayRoutes.budgets),
    ('goals', OkayRoutes.goals),
    ('bills', OkayRoutes.bills),
    ('alerts', OkayRoutes.alerts),
    ('settings', OkayRoutes.settings),
  ]) {
    testWidgets(name, (t) async {
      await _pumpHost(t);
      await _open(t, path);
      await _matches(name);
    });
  }

  testWidgets('budget sheet', (t) async {
    await _pumpHost(t);
    await _open(t, OkayRoutes.budgets);
    await t.tap(find.text('Groceries'));
    await t.pumpAndSettle();
    await _matches('budget_sheet');
  });

  testWidgets('transaction sheet', (t) async {
    await _pumpHost(t);
    await _open(t, OkayRoutes.transactions);
    await t.tap(find.textContaining('Sasto Mitho Khaja Ghar').first);
    await t.pumpAndSettle();
    await _matches('transaction_sheet');
  });

  testWidgets('insights with the balance hidden', (t) async {
    await _pumpHost(t);
    await hideAmounts(t);
    await _open(t, OkayRoutes.insights);
    await _matches('insights_hidden');
  });
}
