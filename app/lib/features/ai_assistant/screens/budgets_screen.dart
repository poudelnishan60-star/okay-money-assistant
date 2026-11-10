import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/api_client.dart';
import '../core/money.dart';
import '../data/models.dart';
import '../data/providers.dart';
import '../theme/okay_theme.dart';
import '../widgets/widgets.dart';

/// Monthly budgets: progress bars (green < 80%, amber 80-100%, red > 100%), each with words and
/// an icon too; a bottom sheet to create or edit one.
class BudgetsScreen extends ConsumerWidget {
  const BudgetsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final budgets = ref.watch(budgetsProvider);
    return OkayScaffold(
      title: 'Budgets',
      actions: [
        IconButton(
          tooltip: 'New budget',
          onPressed: () => showBudgetSheet(context, existing: budgets.value ?? const []),
          icon: const Icon(Icons.add_rounded),
        ),
      ],
      body: AsyncBody(
        value: budgets,
        onRetry: () => ref.invalidate(budgetsProvider),
        onRefresh: () => ref.refresh(budgetsProvider.future),
        data: (list) => list.isEmpty
            ? EmptyView(
                icon: Icons.pie_chart_outline_rounded,
                title: 'No budgets yet',
                message: 'Set a monthly limit for all spending or for one category.',
                action: FilledButton(
                  onPressed: () => showBudgetSheet(context, existing: list),
                  child: const Text('New budget'),
                ),
              )
            : ListView(
                padding: const EdgeInsets.fromLTRB(
                  OkaySpacing.gutter,
                  OkaySpacing.sm,
                  OkaySpacing.gutter,
                  OkaySpacing.xxl,
                ),
                children: [
                  for (final b in list)
                    Padding(
                      padding: const EdgeInsets.only(bottom: OkaySpacing.md),
                      child: _BudgetCard(
                        b,
                        onTap: () => showBudgetSheet(context, existing: list, editing: b),
                      ),
                    ),
                  const SizedBox(height: OkaySpacing.sm),
                  OutlinedButton.icon(
                    onPressed: () => showBudgetSheet(context, existing: list),
                    icon: const Icon(Icons.add_rounded),
                    label: const Text('New budget'),
                  ),
                  const SizedBox(height: OkaySpacing.md),
                  const Text(
                    'Budgets count spending only: transfers to people, Smart Deposit and income '
                    "aren't included. You get alerts at 80% and 100%.",
                    style: OkayText.caption,
                  ),
                ],
              ),
      ),
    );
  }
}

class _BudgetCard extends StatelessWidget {
  const _BudgetCard(this.b, {required this.onTap});
  final Budget b;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final (icon, words) = switch (b.level) {
      'over' => (Icons.error_outline, 'Over budget'),
      'warning' => (Icons.warning_amber_rounded, 'Near the limit'),
      _ => (Icons.check_circle_outline, 'On track'),
    };
    return OkayCard(
      onTap: onTap,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(child: Text(b.name, style: OkayText.rowTitle)),
              Text(
                '${b.period.label}${b.calendar == 'BS' ? ' (BS)' : ''}',
                style: OkayText.caption,
              ),
            ],
          ),
          const SizedBox(height: OkaySpacing.sm),
          Wrap(
            crossAxisAlignment: WrapCrossAlignment.end,
            children: [
              AmountText(b.spentPaisa, style: OkayText.amount.copyWith(fontSize: 20)),
              const Text('  of  ', style: OkayText.subtitle),
              AmountText(b.limitPaisa, style: OkayText.subtitle),
            ],
          ),
          const SizedBox(height: OkaySpacing.sm),
          BudgetProgressBar(percentUsed: b.percentUsed),
          const SizedBox(height: OkaySpacing.sm),
          Row(
            children: [
              Icon(icon, size: 16, color: budgetColor(b.percentUsed)),
              const SizedBox(width: 6),
              Text('$words · ${b.percentUsed.toStringAsFixed(0)}%', style: OkayText.caption),
            ],
          ),
          const SizedBox(height: 4),
          if (b.remainingPaisa >= 0)
            Wrap(
              children: [
                AmountText(
                  b.remainingPaisa,
                  style: OkayText.caption.copyWith(color: OkayColors.text),
                ),
                const Text(' left · about ', style: OkayText.caption),
                AmountText(
                  b.dailyAllowancePaisa,
                  style: OkayText.caption.copyWith(color: OkayColors.text),
                ),
                Text(
                  ' a day for ${b.daysLeft} day${b.daysLeft == 1 ? '' : 's'}',
                  style: OkayText.caption,
                ),
              ],
            )
          else
            Wrap(
              children: [
                const Text('Over by ', style: OkayText.caption),
                AmountText(
                  -b.remainingPaisa,
                  style: OkayText.caption.copyWith(color: OkayColors.danger),
                ),
              ],
            ),
        ],
      ),
    );
  }
}

/// Create (category not yet budgeted, or Overall) or edit (limit, AD/BS month, delete).
Future<void> showBudgetSheet(
  BuildContext context, {
  required List<Budget> existing,
  Budget? editing,
}) => showModalBottomSheet<void>(
  context: context,
  isScrollControlled: true,
  builder: (context) => _BudgetSheet(existing: existing, editing: editing),
);

class _BudgetSheet extends ConsumerStatefulWidget {
  const _BudgetSheet({required this.existing, this.editing});
  final List<Budget> existing;
  final Budget? editing;

  @override
  ConsumerState<_BudgetSheet> createState() => _BudgetSheetState();
}

class _BudgetSheetState extends ConsumerState<_BudgetSheet> {
  static const _overall = 'Overall';
  late final _amount = TextEditingController(
    text: widget.editing == null ? '' : rupeesInput(widget.editing!.limitPaisa),
  );
  late String? _category = widget.editing == null ? null : (widget.editing!.category ?? _overall);
  late String _calendar = widget.editing?.calendar ?? 'AD';
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _amount.dispose();
    super.dispose();
  }

  Future<void> _run(Future<void> Function(BudgetsController c) action) async {
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await action(ref.read(budgetsProvider.notifier));
      if (mounted) Navigator.of(context).pop();
    } on ApiException catch (e) {
      setState(() {
        _saving = false;
        _error = e.message;
      });
    }
  }

  void _save() {
    final paisa = parseRupees(_amount.text);
    if (_category == null || paisa == null) {
      setState(
        () => _error = _category == null ? 'Choose a category.' : 'Enter an amount above 0.',
      );
      return;
    }
    final editing = widget.editing;
    _run(
      (c) => editing == null
          ? c.upsert(
              category: _category == _overall ? null : _category,
              limitPaisa: paisa,
              calendar: _calendar,
            )
          : c.edit(editing.id, limitPaisa: paisa, calendar: _calendar),
    );
  }

  @override
  Widget build(BuildContext context) {
    final editing = widget.editing;
    final categories = ref.watch(categoriesProvider).value ?? const <CategoryInfo>[];
    final taken = {for (final b in widget.existing) b.category ?? _overall};
    final choices = [
      _overall,
      for (final c in categories)
        if (c.countsAsSpending && c.name != 'Other') c.name,
    ].where((c) => editing != null || !taken.contains(c)).toList();
    return SafeArea(
      child: SingleChildScrollView(
        padding: EdgeInsets.fromLTRB(
          OkaySpacing.xl,
          0,
          OkaySpacing.xl,
          OkaySpacing.xl + MediaQuery.viewInsetsOf(context).bottom,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              editing == null ? 'New budget' : '${editing.name} budget',
              style: OkayText.sectionTitle,
            ),
            const SizedBox(height: OkaySpacing.lg),
            if (editing == null) ...[
              const Text('Category', style: OkayText.subtitle),
              const SizedBox(height: OkaySpacing.sm),
              DropdownButtonFormField<String>(
                initialValue: _category,
                isExpanded: true,
                hint: const Text('Choose'),
                items: [for (final c in choices) DropdownMenuItem(value: c, child: Text(c))],
                onChanged: (v) => setState(() => _category = v),
              ),
              const SizedBox(height: OkaySpacing.lg),
            ],
            const Text('Monthly limit (Rs.)', style: OkayText.subtitle),
            const SizedBox(height: OkaySpacing.sm),
            TextField(
              controller: _amount,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(hintText: 'e.g. 6,000'),
              style: OkayText.body,
            ),
            const SizedBox(height: OkaySpacing.lg),
            const Text('Month', style: OkayText.subtitle),
            const SizedBox(height: OkaySpacing.sm),
            Wrap(
              spacing: OkaySpacing.sm,
              runSpacing: OkaySpacing.sm,
              children: [
                PillChip(
                  label: 'AD month',
                  selected: _calendar == 'AD',
                  onTap: () => setState(() => _calendar = 'AD'),
                ),
                PillChip(
                  label: 'Nepali (BS) month',
                  selected: _calendar == 'BS',
                  onTap: () => setState(() => _calendar = 'BS'),
                ),
              ],
            ),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(top: OkaySpacing.md),
                child: Text(_error!, style: OkayText.caption.copyWith(color: OkayColors.warning)),
              ),
            const SizedBox(height: OkaySpacing.xl),
            FilledButton(
              onPressed: _saving ? null : _save,
              child: _saving
                  ? const SizedBox.square(
                      dimension: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text('Save'),
            ),
            if (editing != null) ...[
              const SizedBox(height: OkaySpacing.sm),
              TextButton(
                onPressed: _saving ? null : () => _run((c) => c.remove(editing.id)),
                child: const Text('Delete this budget'),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
