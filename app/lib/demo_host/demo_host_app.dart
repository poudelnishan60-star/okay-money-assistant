// The public website's shell: it opens straight into the O-Kay chat, with no stand-in Khalti
// home screen around it. It plays the host app's part in the smallest way: it mounts the
// assistant's routes, supplies the mock bridge ("would open X" sheets) and draws the website
// frame. Nothing under lib/features/ai_assistant/ imports from here; this file only uses the
// feature's public API (ai_assistant.dart), exactly like the real app will.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../features/ai_assistant/ai_assistant.dart';
import 'web_frame.dart';

GoRouter buildDemoRouter(GlobalKey<NavigatorState> rootNavigatorKey) => GoRouter(
  navigatorKey: rootNavigatorKey,
  initialLocation: '/',
  routes: [
    GoRoute(
      path: '/',
      // The chat is the front page. With the feature flag off there is nothing to open.
      redirect: (context, state) =>
          ProviderScope.containerOf(context).read(aiAssistantEnabledProvider)
          ? OkayRoutes.chat
          : null,
      builder: (context, state) => const _SwitchedOff(),
    ),
    ...aiAssistantRoutes(parentNavigatorKey: rootNavigatorKey),
  ],
);

class DemoHostApp extends ConsumerStatefulWidget {
  const DemoHostApp({super.key, required this.navigatorKey});

  final GlobalKey<NavigatorState> navigatorKey;

  @override
  ConsumerState<DemoHostApp> createState() => _DemoHostAppState();
}

class _DemoHostAppState extends ConsumerState<DemoHostApp> {
  late final GoRouter _router = buildDemoRouter(widget.navigatorKey);

  @override
  void dispose() {
    _router.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'O-Kay · unofficial prototype',
      debugShowCheckedModeBanner: false,
      theme: buildOkayTheme(),
      routerConfig: _router,
      builder: (context, child) => WebFrame(child: child ?? const SizedBox.shrink()),
    );
  }
}

/// Shown only when the feature flag is off (OKAY_AI_ENABLED=false).
class _SwitchedOff extends StatelessWidget {
  const _SwitchedOff();

  @override
  Widget build(BuildContext context) => const Scaffold(
    body: EmptyView(
      icon: Icons.power_settings_new_rounded,
      title: 'O-Kay is switched off',
      message: 'The assistant is turned off in this build.',
    ),
  );
}

/// Wires the demo: the mock bridge stands in for the Khalti app's flows.
Widget buildDemoApp() {
  final navigatorKey = GlobalKey<NavigatorState>();
  return ProviderScope(
    overrides: [hostAppBridgeProvider.overrideWithValue(MockHostAppBridge(navigatorKey))],
    child: DemoHostApp(navigatorKey: navigatorKey),
  );
}
