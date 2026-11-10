import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/api_client.dart';
import '../core/dates.dart';
import '../core/preferences.dart';
import '../data/models.dart';
import '../data/providers.dart';
import '../host/host_app_bridge.dart';
import '../theme/okay_theme.dart';
import '../widgets/widgets.dart';

/// Bills & subscriptions detected from the user's payments: next due date, usual amount,
/// Pay now / Set up Autopay (the host app's own flows), confirm or dismiss each detection.
class BillsScreen extends ConsumerStatefulWidget {
  const BillsScreen({super.key});

  @override
  ConsumerState<BillsScreen> createState() => _BillsScreenState();
}

class _BillsScreenState extends ConsumerState<BillsScreen> {
  bool _showDismissed = false;

  Future<void> _setStatus(Bill b, String status) async {
    try {
      await ref.read(billsProvider.notifier).setStatus(b.id, status);
    } on ApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final bills = ref.watch(billsProvider);
    return OkayScaffold(
      title: 'Bills & subscriptions',
      body: AsyncBody(
        value: bills,
        onRetry: () => ref.invalidate(billsProvider),
        data: (all) {
          final active = all.where((b) => b.status != 'dismissed').toList();
          final dismissed = all.where((b) => b.status == 'dismissed').toList();
          return ListView(
            padding: const EdgeInsets.fromLTRB(
              OkaySpacing.gutter,
              OkaySpacing.sm,
              OkaySpacing.gutter,
              OkaySpacing.xxl,
            ),
            children: [
              const Text(
                'Found in your payments: the same biller, a similar amount, at regular intervals. '
                'Confirm the ones that are right, or dismiss the rest.',
                style: OkayText.caption,
              ),
              const SizedBox(height: OkaySpacing.md),
              if (active.isEmpty)
                const EmptyView(
                  icon: Icons.event_repeat_outlined,
                  title: 'No recurring payments found',
                ),
              for (final b in active)
                Padding(
                  padding: const EdgeInsets.only(bottom: OkaySpacing.md),
                  child: _BillCard(
                    b,
                    onConfirm: () => _setStatus(b, 'confirmed'),
                    onDismiss: () => _setStatus(b, 'dismissed'),
                  ),
                ),
              if (dismissed.isNotEmpty) ...[
                TextButton.icon(
                  onPressed: () => setState(() => _showDismissed = !_showDismissed),
                  icon: Icon(_showDismissed ? Icons.expand_less : Icons.expand_more),
                  label: Text('Dismissed (${dismissed.length})'),
                ),
                if (_showDismissed)
                  for (final b in dismissed)
                    MenuRow(
                      icon: Icons.block_outlined,
                      title: b.merchant,
                      subtitle: 'Not treated as a bill',
                      trailing: TextButton(
                        onPressed: () => _setStatus(b, 'detected'),
                        child: const Text('Undo'),
                      ),
                    ),
              ],
            ],
          );
        },
      ),
    );
  }
}

/// Less side padding so "Set up Autopay" fits on one line in half a phone's width.
final _tight = ButtonStyle(
  padding: WidgetStateProperty.all(const EdgeInsets.symmetric(horizontal: 12)),
);

class _BillCard extends ConsumerWidget {
  const _BillCard(this.b, {required this.onConfirm, required this.onDismiss});
  final Bill b;
  final VoidCallback onConfirm;
  final VoidCallback onDismiss;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final calendar = ref.watch(assistantPrefsProvider.select((p) => p.calendar));
    final bridge = ref.watch(hostAppBridgeProvider);
    final soon = b.overdue || b.daysUntilDue <= 3;
    final due = b.overdue
        ? 'Overdue by ${-b.daysUntilDue} day${b.daysUntilDue == -1 ? '' : 's'}'
        : b.daysUntilDue == 0
        ? 'Due today'
        : 'Due in ${b.daysUntilDue} day${b.daysUntilDue == 1 ? '' : 's'}';
    final visual = transactionVisual(b.service == null ? 'scan_pay' : 'bill_payment', b.service);
    return OkayCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: OkayColors.iconTileBackground,
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Icon(visual.icon, color: OkayColors.iconTileForeground, size: 22),
              ),
              const SizedBox(width: OkaySpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(b.merchant, style: OkayText.rowTitle.copyWith(fontSize: 17)),
                    Text('${b.subcategory ?? b.category} · ${b.cadence}', style: OkayText.caption),
                    const SizedBox(height: 4),
                    Row(
                      children: [
                        if (soon) ...[
                          const Icon(Icons.schedule, size: 14, color: OkayColors.warning),
                          const SizedBox(width: 4),
                        ],
                        Flexible(
                          child: Text(
                            '$due · ${formatShortDate(b.dueDate, calendar)}',
                            style: OkayText.caption.copyWith(
                              color: soon ? OkayColors.warning : OkayColors.textSecondary,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  const Text('Usually', style: OkayText.caption),
                  AmountText(b.usualAmountPaisa, style: OkayText.amount),
                ],
              ),
            ],
          ),
          const SizedBox(height: OkaySpacing.md),
          Row(
            children: [
              Expanded(
                child: FilledButton(
                  style: _tight,
                  onPressed: b.service == null
                      ? null
                      : () => bridge.openBillPayment(
                          b.service!,
                          BillPaymentPrefill(
                            billerName: b.merchant,
                            amountPaisa: b.usualAmountPaisa,
                          ),
                        ),
                  child: const Text('Pay now'),
                ),
              ),
              const SizedBox(width: OkaySpacing.sm),
              Expanded(
                child: OutlinedButton(
                  style: _tight,
                  onPressed: () => bridge.openAutopay(service: b.service),
                  child: const Text('Set up Autopay'),
                ),
              ),
            ],
          ),
          const SizedBox(height: OkaySpacing.xs),
          Row(
            children: [
              if (b.status == 'confirmed')
                const Expanded(
                  child: Row(
                    children: [
                      Icon(Icons.verified_outlined, size: 16, color: OkayColors.positive),
                      SizedBox(width: 4),
                      Text('Confirmed as a bill', style: OkayText.caption),
                    ],
                  ),
                )
              else ...[
                const Expanded(child: Text('Is this a regular bill?', style: OkayText.caption)),
                TextButton.icon(
                  onPressed: onConfirm,
                  icon: const Icon(Icons.check_rounded, size: 18),
                  label: const Text('Yes'),
                ),
              ],
              TextButton.icon(
                onPressed: onDismiss,
                icon: const Icon(Icons.close_rounded, size: 18),
                label: const Text('Dismiss'),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
