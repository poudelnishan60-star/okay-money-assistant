import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'chat/chat_screen.dart';
import 'config.dart';
import 'data/models.dart';
import 'data/providers.dart';
import 'screens/alerts_screen.dart';
import 'screens/bills_screen.dart';
import 'screens/budgets_screen.dart';
import 'screens/goals_screen.dart';
import 'screens/insights_screen.dart';
import 'screens/settings_screen.dart';
import 'screens/transactions_screen.dart';
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

  /// Budget, bill, unusual-spending and weekly-summary alerts.
  static const alerts = '/assistant/alerts';
  static const uiKit = '/assistant/ui-kit';
}

/// Every assistant route, behind the feature flag: with the flag off they redirect to '/'.
/// Pass the host's root navigator key so assistant screens cover the host's bottom bar.
/// A host with its own look passes [theme] (usually [buildOkayTheme]) to show the assistant's
/// pages in theirs. (Not a ShellRoute: its separate navigator would hide the back arrow.)
List<RouteBase> aiAssistantRoutes({
  GlobalKey<NavigatorState>? parentNavigatorKey,
  ThemeData? theme,
}) => [
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
        builder: (context, state) => _Root(const ChatScreen(), theme: theme),
      ),
      GoRoute(
        path: 'insights',
        builder: (context, state) => _Root(const InsightsScreen(), theme: theme),
      ),
      GoRoute(
        path: 'transactions',
        builder: (context, state) => _Root(
          theme: theme,
          TransactionsScreen(
            // Opened from a chat link or a dashboard tap: start with those filters.
            initial: state.uri.queryParameters.isEmpty
                ? const TxnQuery(period: '30d')
                : TxnQuery.fromParams(state.uri.queryParameters),
          ),
        ),
      ),
      GoRoute(
        path: 'budgets',
        builder: (context, state) => _Root(const BudgetsScreen(), theme: theme),
      ),
      GoRoute(
        path: 'goals',
        builder: (context, state) => _Root(const GoalsScreen(), theme: theme),
      ),
      GoRoute(
        path: 'bills',
        builder: (context, state) => _Root(const BillsScreen(), theme: theme),
      ),
      GoRoute(
        path: 'settings',
        builder: (context, state) => _Root(const SettingsScreen(), theme: theme),
      ),
      GoRoute(
        path: 'alerts',
        builder: (context, state) => _Root(const AlertsScreen(), theme: theme),
      ),
      GoRoute(path: 'ui-kit', builder: (context, state) => const UiKitScreen()),
    ],
  ),
];

/// Wraps every assistant screen: keeps the user's saved settings (language, calendar) loaded,
/// so all screens and the chat use them from the first frame they are available.
class _Root extends ConsumerWidget {
  const _Root(this.child, {this.theme});
  final Widget child;
  final ThemeData? theme;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.watch(settingsProvider);
    final look = theme;
    return look == null ? child : Theme(data: look, child: child);
  }
}
