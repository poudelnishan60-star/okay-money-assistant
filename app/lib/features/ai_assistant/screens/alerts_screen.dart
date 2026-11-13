import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../chat/message_text.dart';
import '../core/dates.dart';
import '../core/preferences.dart';
import '../data/models.dart';
import '../data/providers.dart';
import '../routes.dart';
import '../theme/okay_theme.dart';
import '../widgets/widgets.dart';

/// O-Kay's alerts: a budget at 80% or 100%, a bill due within 3 days, unusual spending, and
/// the weekly summary. Tapping one marks it read and opens the screen it is about.
class AlertsScreen extends ConsumerWidget {
  const AlertsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final inbox = ref.watch(alertsProvider);
    final unread = inbox.value?.unread ?? 0;
    return OkayScaffold(
      title: 'Alerts',
      actions: [
        if (unread > 0)
          TextButton(
            onPressed: () => ref.read(alertsProvider.notifier).markAllRead(),
            child: const Text('Mark all read'),
          ),
      ],
      body: AsyncBody(
        value: inbox,
        onRetry: () => ref.invalidate(alertsProvider),
        data: (inbox) {
          if (inbox.items.isEmpty) {
            return EmptyView(
              icon: Icons.notifications_none_outlined,
              title: 'No alerts yet',
              message:
                  'O-Kay tells you here when a budget reaches 80% or 100%, a bill is due within '
                  '3 days, or spending looks unusual, and sends a weekly summary.',
              action: OutlinedButton(
                onPressed: () => context.push(OkayRoutes.settings),
                child: const Text('Alert settings'),
              ),
            );
          }
          final fresh = inbox.items.where((n) => !n.read).toList();
          final earlier = inbox.items.where((n) => n.read).toList();
          return RefreshIndicator(
            onRefresh: () => ref.refresh(alertsProvider.future),
            child: ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.only(bottom: OkaySpacing.xxl),
              children: [
                if (fresh.isNotEmpty) ...[
                  const _Heading('New'),
                  for (final n in fresh) _AlertRow(n),
                ],
                if (earlier.isNotEmpty) ...[
                  const _Heading('Earlier'),
                  for (final n in earlier) _AlertRow(n),
                ],
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: OkaySpacing.gutter),
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: TextButton.icon(
                      onPressed: () => context.push(OkayRoutes.settings),
                      icon: const Icon(Icons.tune_rounded, size: 18),
                      label: const Text('Choose which alerts you get'),
                    ),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _Heading extends StatelessWidget {
  const _Heading(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.fromLTRB(
      OkaySpacing.gutter,
      OkaySpacing.lg,
      OkaySpacing.gutter,
      OkaySpacing.xs,
    ),
    child: Text(text, style: OkayText.subtitle.copyWith(fontWeight: FontWeight.w600)),
  );
}

/// The app path an alert opens.
String alertRoute(AlertLink link) => switch (link.screen) {
  'budgets' => OkayRoutes.budgets,
  'bills' => OkayRoutes.bills,
  'transactions' => Uri(
    path: OkayRoutes.transactions,
    queryParameters: link.params.isEmpty ? null : link.params,
  ).toString(),
  _ => OkayRoutes.insights,
};

IconData _icon(String kind) => switch (kind) {
  'budget' => Icons.pie_chart_outline_rounded,
  'bill' => Icons.event_repeat_outlined,
  'unusual' => Icons.trending_up_rounded,
  _ => Icons.insights_outlined,
};

class _AlertRow extends ConsumerWidget {
  const _AlertRow(this.n);
  final AlertItem n;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final calendar = ref.watch(assistantPrefsProvider.select((p) => p.calendar));
    return Semantics(
      button: true,
      hint: n.read ? null : 'Unread',
      child: InkWell(
        onTap: () {
          ref.read(alertsProvider.notifier).markRead(n.id);
          context.push(alertRoute(n.link));
        },
        child: Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: OkaySpacing.gutter,
            vertical: OkaySpacing.md,
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: OkayColors.iconTileBackground,
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Icon(_icon(n.kind), color: OkayColors.iconTileForeground, size: 22),
              ),
              const SizedBox(width: OkaySpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    MessageText(
                      n.title,
                      style: OkayText.body.copyWith(
                        fontWeight: n.read ? FontWeight.w500 : FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 2),
                    // Bodies carry amounts: MessageText masks them while the balance is hidden.
                    MessageText(n.body, style: OkayText.subtitle),
                    const SizedBox(height: OkaySpacing.xs),
                    Text(formatShortDate(n.day, calendar), style: OkayText.caption),
                  ],
                ),
              ),
              if (!n.read)
                const Padding(
                  padding: EdgeInsets.only(left: OkaySpacing.sm, top: 6),
                  child: CircleAvatar(radius: 4, backgroundColor: OkayColors.accentPink),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// A bell with the unread count; opens [AlertsScreen]. Used on the Insights screen; the host
/// app can put it (or [unreadAlertsProvider] on its own bell) wherever it likes.
class AlertsBell extends ConsumerWidget {
  const AlertsBell({super.key, this.compact = false});

  /// A smaller tap area, for headers with several actions.
  final bool compact;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final unread = ref.watch(unreadAlertsProvider);
    return IconButton(
      tooltip: unread == 0 ? 'Alerts' : 'Alerts, $unread unread',
      visualDensity: compact ? VisualDensity.compact : null,
      onPressed: () => context.push(OkayRoutes.alerts),
      icon: Badge(
        isLabelVisible: unread > 0,
        label: Text('$unread'),
        backgroundColor: OkayColors.primary,
        textColor: OkayColors.text,
        child: const Icon(Icons.notifications_none_outlined),
      ),
    );
  }
}
