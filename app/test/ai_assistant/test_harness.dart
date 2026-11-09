import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:khalti_ai_assistant/demo_host/demo_host_app.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/ai_assistant.dart';

const demoMe = Me(
  id: 'demo_user',
  name: 'Anjali Thapa',
  balancePaisa: 2394486,
  balanceHidden: false,
);

/// Phone-sized test surface (390 x 844 logical pixels).
void usePhoneSize(WidgetTester tester) {
  tester.view.physicalSize = const Size(390 * 3, 844 * 3);
  tester.view.devicePixelRatio = 3;
  addTearDown(tester.view.reset);
}

/// A widget inside the assistant theme and a ProviderScope.
Widget themed(Widget child, {List<Override> overrides = const []}) => ProviderScope(
  overrides: overrides,
  child: MaterialApp(
    theme: buildOkayTheme(),
    home: Scaffold(body: child),
  ),
);

/// The whole demo host with no network: /me is faked.
({Widget app, MockHostAppBridge bridge}) demoApp({bool enabled = true}) {
  final key = GlobalKey<NavigatorState>();
  final bridge = MockHostAppBridge(key);
  return (
    app: ProviderScope(
      overrides: [
        hostAppBridgeProvider.overrideWithValue(bridge),
        aiAssistantEnabledProvider.overrideWithValue(enabled),
        meProvider.overrideWith((ref) async => demoMe),
      ],
      child: DemoHostApp(navigatorKey: key),
    ),
    bridge: bridge,
  );
}
