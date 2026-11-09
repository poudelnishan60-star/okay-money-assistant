// Demo host: a stand-in for the Khalti app so the assistant can be run and reviewed on its
// own. Nothing under lib/features/ai_assistant/ imports from here; this file only uses the
// feature's public API (ai_assistant.dart), exactly like the real app will.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../features/ai_assistant/ai_assistant.dart';
import 'home_screen.dart';
import 'host_shell.dart';
import 'web_frame.dart';

GoRouter buildDemoRouter(GlobalKey<NavigatorState> rootNavigatorKey) => GoRouter(
  navigatorKey: rootNavigatorKey,
  initialLocation: '/',
  routes: [
    StatefulShellRoute.indexedStack(
      builder: (context, state, shell) => HostShell(shell: shell),
      branches: [
        StatefulShellBranch(
          routes: [GoRoute(path: '/', builder: (context, state) => const HomeScreen())],
        ),
        StatefulShellBranch(
          routes: [
            GoRoute(
              path: '/cards',
              builder: (context, state) => const HostPlaceholderTab(title: 'Cards'),
            ),
          ],
        ),
        StatefulShellBranch(
          routes: [
            GoRoute(
              path: '/transaction',
              builder: (context, state) => const HostPlaceholderTab(
                title: 'Transaction',
                linkLabel: 'Open the assistant’s transaction view',
                linkPath: OkayRoutes.transactions,
              ),
            ),
          ],
        ),
        StatefulShellBranch(
          routes: [GoRoute(path: '/menu', builder: (context, state) => const MenuTab())],
        ),
      ],
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

/// Wires the demo: the mock bridge stands in for the Khalti app's flows.
Widget buildDemoApp() {
  final navigatorKey = GlobalKey<NavigatorState>();
  return ProviderScope(
    overrides: [hostAppBridgeProvider.overrideWithValue(MockHostAppBridge(navigatorKey))],
    child: DemoHostApp(navigatorKey: navigatorKey),
  );
}
