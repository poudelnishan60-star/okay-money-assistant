import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'config.dart';
import 'screens/coming_soon_screen.dart';
import 'screens/ui_kit_screen.dart';

/// Paths of the assistant's screens. The host mounts [aiAssistantRoutes] in its router.
abstract final class OkayRoutes {
  static const root = '/assistant';
  static const chat = '/assistant/chat';
  static const insights = '/assistant/insights';

  /// Accepts the same filters as GET /transactions, e.g.
  /// /assistant/transactions?category=Food%20%26%20Dining&period=this_month
  static const transactions = '/assistant/transactions';
  static const budgets = '/assistant/budgets';
  static const goals = '/assistant/goals';
  static const bills = '/assistant/bills';
  static const settings = '/assistant/settings';
  static const uiKit = '/assistant/ui-kit';
}

/// Every assistant route, behind the feature flag: with the flag off they redirect to '/'.
/// Pass the host's root navigator key so assistant screens cover the host's bottom bar.
List<RouteBase> aiAssistantRoutes({GlobalKey<NavigatorState>? parentNavigatorKey}) => [
  GoRoute(
    path: OkayRoutes.root,
    parentNavigatorKey: parentNavigatorKey,
    redirect: (context, state) {
      final enabled = ProviderScope.containerOf(context).read(aiAssistantEnabledProvider);
      if (!enabled) return '/';
      if (state.uri.path == OkayRoutes.root) return OkayRoutes.insights;
      return null;
    },
    routes: [
      GoRoute(
        path: 'chat',
        builder: (context, state) => const ComingSoonScreen(
          title: 'O-Kay',
          step: 7,
          note: 'Chat with your money: streamed answers, cards and follow-up chips.',
        ),
      ),
      GoRoute(
        path: 'insights',
        builder: (context, state) => const ComingSoonScreen(title: 'Money Insights', step: 5),
      ),
      GoRoute(
        path: 'transactions',
        builder: (context, state) => const ComingSoonScreen(title: 'Transactions', step: 5),
      ),
      GoRoute(
        path: 'budgets',
        builder: (context, state) => const ComingSoonScreen(title: 'Budgets', step: 5),
      ),
      GoRoute(
        path: 'goals',
        builder: (context, state) => const ComingSoonScreen(title: 'Savings goals', step: 5),
      ),
      GoRoute(
        path: 'bills',
        builder: (context, state) =>
            const ComingSoonScreen(title: 'Bills & subscriptions', step: 5),
      ),
      GoRoute(
        path: 'settings',
        builder: (context, state) => const ComingSoonScreen(title: 'Assistant settings', step: 5),
      ),
      GoRoute(path: 'ui-kit', builder: (context, state) => const UiKitScreen()),
    ],
  ),
];
