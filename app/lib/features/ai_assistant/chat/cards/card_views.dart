import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/dates.dart';
import '../../core/preferences.dart';
import '../../host/host_app_bridge.dart';
import '../../routes.dart';
import '../../theme/okay_theme.dart';
import '../../widgets/widgets.dart';
import '../chat_controller.dart';
import '../chat_models.dart';

/// Renders one card from an answer. [messageIndex]/[cardIndex] identify confirm cards.
class ChatCardView extends StatelessWidget {
  const ChatCardView({
    super.key,
    required this.card,
    required this.messageIndex,
    required this.cardIndex,
  });

  final ChatCard card;
  final int messageIndex;
  final int cardIndex;

  @override
  Widget build(BuildContext context) {
    return switch (card) {
      final SpendingSummaryCard c => _SpendingSummary(c),
      final CategoryBreakdownCard c => _CategoryBreakdown(c),
      final BudgetProgressCard c => _BudgetProgress(c),
      final BillsListCard c => _BillsList(c),
      final GoalProgressCard c => _GoalProgress(c),
      final TransactionsPreviewCard c => _TransactionsPreview(c),
      final ConfirmActionCard c => _ConfirmAction(c, messageIndex, cardIndex),
      final OpenAppFlowCard c => _OpenAppFlow(c),
      UnknownCard() => const SizedBox.shrink(),
    };
  }
}

// --- shared pieces ----------------------------------------------------------------------

class _Frame extends StatelessWidget {
  const _Frame({required this.title, required this.children, this.icon});

  final String title;
  final IconData? icon;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(OkaySpacing.lg),
      decoration: BoxDecoration(
        color: OkayColors.surface,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: OkayColors.divider),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              if (icon != null) ...[
                Icon(icon, size: 18, color: OkayColors.iconTileForeground),
                const SizedBox(width: OkaySpacing.sm),
              ],
              Expanded(
                child: Text(title, style: OkayText.subtitle.copyWith(color: OkayColors.text)),
              ),
            ],
          ),
          const SizedBox(height: OkaySpacing.md),
          ...children,
        ],
      ),
    );
  }
}

/// "View 12 transactions ->" opens the transactions screen with the answer's filters.
class TransactionsLinkButton extends StatelessWidget {
  const TransactionsLinkButton(this.link, {super.key});
  final TransactionsLink link;

  @override
  Widget build(BuildContext context) {
    final n = link.count;
    return Align(
      alignment: Alignment.centerLeft,
      child: TextButton(
        style: TextButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 4)),
        onPressed: () => context.push(
          Uri(path: OkayRoutes.transactions, queryParameters: link.filters).toString(),
        ),
        child: Text('View $n transaction${n == 1 ? '' : 's'} →'),
      ),
    );
  }
}

String _due(int days, bool overdue) {
  if (overdue) return 'Overdue by ${-days} day${days == -1 ? '' : 's'}';
  if (days == 0) return 'Due today';
  return 'Due in $days day${days == 1 ? '' : 's'}';
}

/// "Label ........ value": the value side wraps instead of pushing past the card's edge.
class _DetailRow extends StatelessWidget {
  const _DetailRow(this.label, this.value);
  final String label;
  final Widget value;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 6),
    // The label may take up to 45% and wraps beyond that; the value fills the rest right up
    // to the card's edge, so long values ("Nepal Electricity Authority") line up on the right.
    child: LayoutBuilder(
      builder: (context, c) => Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ConstrainedBox(
            constraints: BoxConstraints(maxWidth: c.maxWidth * 0.45),
            child: Text(label, style: OkayText.caption),
          ),
          const SizedBox(width: OkaySpacing.md),
          Expanded(
            child: Align(alignment: Alignment.topRight, child: value),
          ),
        ],
      ),
    ),
  );
}

// --- spending ---------------------------------------------------------------------------

class _SpendingSummary extends StatelessWidget {
  const _SpendingSummary(this.card);
  final SpendingSummaryCard card;

  @override
  Widget build(BuildContext context) {
    final pct = card.changePercent;
    final down = pct != null && pct < 0;
    final (icon, color, words) = switch (pct) {
      null => (Icons.remove, OkayColors.textSecondary, 'No comparison'),
      0 => (Icons.remove, OkayColors.textSecondary, 'Same as'),
      _ => (
        down ? Icons.south_rounded : Icons.north_rounded,
        down ? OkayColors.positive : OkayColors.accentPink,
        '${pct.abs().toStringAsFixed(pct.abs() >= 10 ? 0 : 1)}% ${down ? 'less' : 'more'} than',
      ),
    };
    return _Frame(
      icon: Icons.insights_outlined,
      title: 'Spent${card.category != null ? ' on ${card.category}' : ''} · ${card.periodLabel}',
      children: [
        AmountText(card.totalPaisa, style: OkayText.bigNumber.copyWith(fontSize: 28)),
        const SizedBox(height: OkaySpacing.xs),
        Row(
          children: [
            Icon(icon, size: 16, color: color),
            const SizedBox(width: 4),
            Flexible(
              child: Text(
                pct == null ? words : '$words ${card.comparedWith}',
                style: OkayText.caption.copyWith(color: OkayColors.textSecondary),
              ),
            ),
          ],
        ),
        if (pct != null) ...[
          const SizedBox(height: 2),
          Row(
            children: [
              const Text('Then: ', style: OkayText.caption),
              AmountText(card.previousPaisa, style: OkayText.caption),
            ],
          ),
        ],
        TransactionsLinkButton(card.link),
      ],
    );
  }
}

/// Ranked horizontal bars, one hue (part-to-whole read row by row; easier to compare than a
/// donut in a narrow chat card). Shows the top 5 and folds the rest into "Other".
class _CategoryBreakdown extends StatelessWidget {
  const _CategoryBreakdown(this.card);
  final CategoryBreakdownCard card;

  @override
  Widget build(BuildContext context) {
    final items = [...card.items];
    if (items.length > 6) {
      final rest = items.sublist(5);
      items
        ..removeRange(5, items.length)
        ..add(
          CategoryAmount(
            'Other',
            rest.fold(0, (a, b) => a + b.spentPaisa),
            rest.fold(0.0, (a, b) => a + b.sharePercent),
          ),
        );
    }
    final maxSpent = items.fold(1, (a, b) => math.max(a, b.spentPaisa));
    return _Frame(
      icon: Icons.bar_chart_rounded,
      title: 'Where it went · ${card.periodLabel}',
      children: [
        for (final i in items)
          Padding(
            padding: const EdgeInsets.only(bottom: OkaySpacing.md),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(child: Text(i.category, style: OkayText.body.copyWith(fontSize: 14))),
                    Text('${i.sharePercent.toStringAsFixed(0)}%  ', style: OkayText.caption),
                    AmountText(i.spentPaisa, style: OkayText.amount.copyWith(fontSize: 14)),
                  ],
                ),
                const SizedBox(height: 6),
                _Bar(fraction: i.spentPaisa / maxSpent),
              ],
            ),
          ),
      ],
    );
  }
}

class _Bar extends StatelessWidget {
  const _Bar({required this.fraction});
  final double fraction;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, c) => Align(
        alignment: Alignment.centerLeft,
        child: Container(
          height: 8,
          width: math.max(4, c.maxWidth * fraction.clamp(0, 1)),
          decoration: BoxDecoration(
            color: OkayColors.accentPink,
            borderRadius: BorderRadius.circular(4),
          ),
        ),
      ),
    );
  }
}

// --- budgets ----------------------------------------------------------------------------

class _BudgetProgress extends StatelessWidget {
  const _BudgetProgress(this.card);
  final BudgetProgressCard card;

  @override
  Widget build(BuildContext context) {
    return _Frame(
      icon: Icons.pie_chart_outline_rounded,
      title: 'Budgets · ${card.items.isEmpty ? '' : card.items.first.periodLabel}',
      children: [
        for (final b in card.items)
          Padding(
            padding: const EdgeInsets.only(bottom: OkaySpacing.lg),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        b.category ?? 'Overall',
                        style: OkayText.body.copyWith(fontWeight: FontWeight.w500),
                      ),
                    ),
                    AmountText(b.spentPaisa, style: OkayText.amount.copyWith(fontSize: 14)),
                    const Text(' of ', style: OkayText.caption),
                    AmountText(b.limitPaisa, style: OkayText.caption),
                  ],
                ),
                const SizedBox(height: 6),
                BudgetProgressBar(percentUsed: b.percentUsed, height: 8),
                const SizedBox(height: 4),
                _LevelLabel(level: b.level, percent: b.percentUsed),
              ],
            ),
          ),
      ],
    );
  }
}

/// Status colour always comes with an icon and words, never colour alone.
class _LevelLabel extends StatelessWidget {
  const _LevelLabel({required this.level, required this.percent});
  final String level;
  final double percent;

  @override
  Widget build(BuildContext context) {
    final (icon, words) = switch (level) {
      'over' => (Icons.error_outline, 'Over budget'),
      'warning' => (Icons.warning_amber_rounded, 'Near the limit'),
      _ => (Icons.check_circle_outline, 'On track'),
    };
    final color = budgetColor(percent);
    return Row(
      children: [
        Icon(icon, size: 14, color: color),
        const SizedBox(width: 4),
        Text('$words · ${percent.toStringAsFixed(0)}% used', style: OkayText.caption),
      ],
    );
  }
}

// --- bills ------------------------------------------------------------------------------

class _BillsList extends ConsumerWidget {
  const _BillsList(this.card);
  final BillsListCard card;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final calendar = ref.watch(assistantPrefsProvider.select((p) => p.calendar));
    final bridge = ref.watch(hostAppBridgeProvider);
    return _Frame(
      icon: Icons.receipt_long_outlined,
      title: 'Upcoming bills',
      children: [
        for (final b in card.items.take(6))
          Padding(
            padding: const EdgeInsets.only(bottom: OkaySpacing.md),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(b.merchant, style: OkayText.body.copyWith(fontSize: 15)),
                      Text(
                        '${_due(b.daysUntilDue, b.overdue)} · '
                        '${formatShortDate(b.dueDate, calendar)}',
                        style: OkayText.caption.copyWith(
                          color: b.overdue || b.daysUntilDue <= 3
                              ? OkayColors.warning
                              : OkayColors.textSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
                AmountText(b.usualAmountPaisa, style: OkayText.amount.copyWith(fontSize: 14)),
                const SizedBox(width: OkaySpacing.sm),
                if (b.service != null)
                  _SmallButton(
                    label: 'Pay',
                    onTap: () => bridge.openBillPayment(
                      b.service!,
                      BillPaymentPrefill(billerName: b.merchant, amountPaisa: b.usualAmountPaisa),
                    ),
                  ),
              ],
            ),
          ),
        OutlinedButton.icon(
          onPressed: () => bridge.openAutopay(),
          icon: const Icon(Icons.autorenew, size: 18),
          label: const Text('Set up Autopay'),
        ),
      ],
    );
  }
}

class _SmallButton extends StatelessWidget {
  const _SmallButton({required this.label, required this.onTap});
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return FilledButton(
      onPressed: onTap,
      style: FilledButton.styleFrom(
        minimumSize: const Size(56, 36),
        padding: const EdgeInsets.symmetric(horizontal: 14),
        textStyle: OkayText.caption.copyWith(fontWeight: FontWeight.w700),
      ),
      child: Text(label),
    );
  }
}

// --- goals ------------------------------------------------------------------------------

class _GoalProgress extends ConsumerWidget {
  const _GoalProgress(this.card);
  final GoalProgressCard card;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final calendar = ref.watch(assistantPrefsProvider.select((p) => p.calendar));
    final bridge = ref.watch(hostAppBridgeProvider);
    final active = card.items.where((g) => g.state == 'active').toList();
    return _Frame(
      icon: Icons.flag_outlined,
      title: 'Savings goals',
      children: [
        for (final g in card.items)
          Padding(
            padding: const EdgeInsets.only(bottom: OkaySpacing.lg),
            child: Row(
              children: [
                ProgressRing(percent: g.percent, size: 52),
                const SizedBox(width: OkaySpacing.md),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(g.name, style: OkayText.body.copyWith(fontWeight: FontWeight.w500)),
                      Wrap(
                        children: [
                          AmountText(g.savedPaisa, style: OkayText.caption),
                          const Text(' of ', style: OkayText.caption),
                          AmountText(g.targetPaisa, style: OkayText.caption),
                        ],
                      ),
                      if (g.state == 'done')
                        const Text('Reached!', style: OkayText.caption)
                      else
                        Wrap(
                          children: [
                            const Text('Needs ', style: OkayText.caption),
                            AmountText(g.requiredMonthlyPaisa, style: OkayText.caption),
                            Text(
                              '/month · by ${formatDate(g.deadline, calendar)}',
                              style: OkayText.caption,
                            ),
                          ],
                        ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        if (active.isNotEmpty)
          FilledButton.icon(
            onPressed: () => bridge.openSmartDeposit(
              prefill: SmartDepositPrefill(
                goalName: active.first.name,
                monthlyAmountPaisa: active.first.requiredMonthlyPaisa,
              ),
            ),
            icon: const Icon(Icons.savings_outlined, size: 18),
            label: const Text('Automate with Smart Deposit'),
          ),
      ],
    );
  }
}

/// Goal progress ring: one hue on a dim track of the same hue, percent in the middle.
class ProgressRing extends StatelessWidget {
  const ProgressRing({super.key, required this.percent, this.size = 52});
  final double percent;
  final double size;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: '${percent.toStringAsFixed(0)} percent saved',
      excludeSemantics: true,
      child: SizedBox.square(
        dimension: size,
        child: Stack(
          alignment: Alignment.center,
          children: [
            SizedBox.square(
              dimension: size,
              child: CircularProgressIndicator(
                value: (percent / 100).clamp(0, 1),
                strokeWidth: 5,
                strokeCap: StrokeCap.round,
                color: OkayColors.accentPink,
                backgroundColor: OkayColors.accentPink.withValues(alpha: 0.18),
              ),
            ),
            Text(
              '${percent.toStringAsFixed(0)}%',
              style: OkayText.caption.copyWith(color: OkayColors.text, fontWeight: FontWeight.w700),
            ),
          ],
        ),
      ),
    );
  }
}

// --- transactions -----------------------------------------------------------------------

class _TransactionsPreview extends ConsumerWidget {
  const _TransactionsPreview(this.card);
  final TransactionsPreviewCard card;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final calendar = ref.watch(assistantPrefsProvider.select((p) => p.calendar));
    return _Frame(
      icon: Icons.receipt_outlined,
      title: '${card.count} transaction${card.count == 1 ? '' : 's'}',
      children: [
        for (final t in card.items)
          Padding(
            padding: const EdgeInsets.only(bottom: OkaySpacing.sm),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(t.merchant, style: OkayText.body.copyWith(fontSize: 14)),
                      Text(
                        '${formatShortDate(t.date, calendar)} · ${t.category}',
                        style: OkayText.caption,
                      ),
                    ],
                  ),
                ),
                AmountText(
                  t.amountPaisa,
                  isDebit: t.isDebit,
                  showArrow: true,
                  style: OkayText.amount.copyWith(fontSize: 14),
                ),
              ],
            ),
          ),
        TransactionsLinkButton(card.link),
      ],
    );
  }
}

// --- confirm / app flow -----------------------------------------------------------------

class _ConfirmAction extends ConsumerWidget {
  const _ConfirmAction(this.card, this.messageIndex, this.cardIndex);
  final ConfirmActionCard card;
  final int messageIndex;
  final int cardIndex;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final key = ChatState.cardKey(messageIndex, cardIndex);
    final status =
        ref.watch(chatControllerProvider.select((s) => s.confirmations[key])) ??
        const ConfirmState(ConfirmStatus.idle);
    final controller = ref.read(chatControllerProvider.notifier);
    return _Frame(
      icon: Icons.task_alt_outlined,
      title: card.title,
      children: [
        for (final (label, value) in card.details)
          _DetailRow(
            label,
            Text(value, style: OkayText.body.copyWith(fontSize: 14), textAlign: TextAlign.end),
          ),
        const SizedBox(height: OkaySpacing.sm),
        switch (status.status) {
          ConfirmStatus.saved => const _Outcome(Icons.check_circle, 'Saved', OkayColors.positive),
          ConfirmStatus.cancelled => const _Outcome(
            Icons.cancel_outlined,
            'Not saved',
            OkayColors.textSecondary,
          ),
          _ => Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (status.status == ConfirmStatus.failed)
                Padding(
                  padding: const EdgeInsets.only(bottom: OkaySpacing.sm),
                  child: Text(
                    status.error ?? 'Could not save.',
                    style: OkayText.caption.copyWith(color: OkayColors.warning),
                  ),
                ),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed: status.status == ConfirmStatus.saving
                          ? null
                          : () => controller.cancelConfirm(messageIndex, cardIndex),
                      child: const Text('Cancel'),
                    ),
                  ),
                  const SizedBox(width: OkaySpacing.md),
                  Expanded(
                    child: FilledButton(
                      onPressed: status.status == ConfirmStatus.saving
                          ? null
                          : () => controller.confirm(messageIndex, cardIndex, card),
                      child: status.status == ConfirmStatus.saving
                          ? const SizedBox.square(
                              dimension: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : Text(
                              status.status == ConfirmStatus.failed
                                  ? 'Try again'
                                  : card.confirmLabel,
                            ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        },
      ],
    );
  }
}

class _Outcome extends StatelessWidget {
  const _Outcome(this.icon, this.text, this.color);
  final IconData icon;
  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) => Row(
    children: [
      Icon(icon, color: color, size: 18),
      const SizedBox(width: 6),
      Text(
        text,
        style: OkayText.body.copyWith(color: color, fontWeight: FontWeight.w600),
      ),
    ],
  );
}

class _OpenAppFlow extends ConsumerWidget {
  const _OpenAppFlow(this.card);
  final OpenAppFlowCard card;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final bridge = ref.watch(hostAppBridgeProvider);
    Future<void> open() => switch (card.flow) {
      'bill_payment' => bridge.openBillPayment(
        card.service ?? 'bill',
        BillPaymentPrefill(billerName: card.billerName, amountPaisa: card.amountPaisa),
      ),
      'send_money' => bridge.openSendMoney(
        SendMoneyPrefill(recipientName: card.recipientName, amountPaisa: card.amountPaisa),
      ),
      'autopay' => bridge.openAutopay(service: card.service),
      _ => bridge.openSmartDeposit(
        prefill: SmartDepositPrefill(
          goalName: card.goalName,
          monthlyAmountPaisa: card.monthlyAmountPaisa,
        ),
      ),
    };
    final lines = <(String, Widget)>[
      if (card.billerName != null)
        ('Biller', Text(card.billerName!, style: OkayText.body, textAlign: TextAlign.end)),
      if (card.recipientName != null)
        ('To', Text(card.recipientName!, style: OkayText.body, textAlign: TextAlign.end)),
      if (card.goalName != null)
        ('Goal', Text(card.goalName!, style: OkayText.body, textAlign: TextAlign.end)),
      if (card.amountPaisa != null)
        ('Amount', AmountText(card.amountPaisa!, style: OkayText.amount.copyWith(fontSize: 14))),
      if (card.monthlyAmountPaisa != null)
        (
          'Every month',
          AmountText(card.monthlyAmountPaisa!, style: OkayText.amount.copyWith(fontSize: 14)),
        ),
    ];
    return _Frame(
      icon: Icons.open_in_new_rounded,
      title: card.title,
      children: [
        for (final (label, value) in lines) _DetailRow(label, value),
        const SizedBox(height: OkaySpacing.sm),
        SizedBox(
          width: double.infinity,
          child: FilledButton.icon(
            onPressed: open,
            icon: const Icon(Icons.lock_outline, size: 18),
            label: Text(card.title),
          ),
        ),
        const SizedBox(height: 6),
        Text(card.note, style: OkayText.caption),
      ],
    );
  }
}
