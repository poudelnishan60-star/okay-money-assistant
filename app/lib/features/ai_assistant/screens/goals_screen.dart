import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/api_client.dart';
import '../core/clock.dart';
import '../core/dates.dart';
import '../core/money.dart';
import '../core/preferences.dart';
import '../data/models.dart';
import '../data/providers.dart';
import '../host/host_app_bridge.dart';
import '../theme/okay_theme.dart';
import '../widgets/widgets.dart';

/// Savings goals: progress ring, target, deadline, "needs Rs. X/month", and "Automate with
/// Smart Deposit" (a deep link: Smart Deposit itself is not rebuilt here).
class GoalsScreen extends ConsumerWidget {
  const GoalsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final goals = ref.watch(goalsProvider);
    final deposits = ref.watch(smartDepositsProvider).value ?? const <SmartDeposit>[];
    return OkayScaffold(
      title: 'Savings goals',
      actions: [
        IconButton(
          tooltip: 'New goal',
          onPressed: () => showGoalSheet(context),
          icon: const Icon(Icons.add_rounded),
        ),
      ],
      body: AsyncBody(
        value: goals,
        onRetry: () => ref.invalidate(goalsProvider),
        onRefresh: () {
          ref.invalidate(smartDepositsProvider);
          return ref.refresh(goalsProvider.future);
        },
        data: (list) => ListView(
          padding: const EdgeInsets.fromLTRB(
            OkaySpacing.gutter,
            OkaySpacing.sm,
            OkaySpacing.gutter,
            OkaySpacing.xxl,
          ),
          children: [
            for (final d in deposits)
              Padding(
                padding: const EdgeInsets.only(bottom: OkaySpacing.md),
                child: _DepositCard(d),
              ),
            if (list.isEmpty)
              const EmptyView(
                icon: Icons.flag_outlined,
                title: 'No goals yet',
                message: 'Save for a laptop, a trip or an emergency fund.',
              ),
            for (final g in list)
              Padding(
                padding: const EdgeInsets.only(bottom: OkaySpacing.md),
                child: _GoalCard(g, onTap: () => showGoalSheet(context, editing: g)),
              ),
            OutlinedButton.icon(
              onPressed: () => showGoalSheet(context),
              icon: const Icon(Icons.add_rounded),
              label: const Text('New goal'),
            ),
          ],
        ),
      ),
    );
  }
}

class _DepositCard extends ConsumerWidget {
  const _DepositCard(this.d);
  final SmartDeposit d;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final calendar = ref.watch(assistantPrefsProvider.select((p) => p.calendar));
    return OkayCard(
      color: OkayColors.surfaceElevated,
      child: Row(
        children: [
          const Icon(Icons.savings_outlined, color: OkayColors.gold),
          const SizedBox(width: OkaySpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(d.name, style: OkayText.body.copyWith(fontWeight: FontWeight.w600)),
                Wrap(
                  children: [
                    AmountText(d.installmentPaisa, style: OkayText.caption),
                    Text(
                      d.nextDate == null
                          ? ' each time'
                          : ' next on ${formatShortDate(d.nextDate!, calendar)}',
                      style: OkayText.caption,
                    ),
                    const Text(' · saved so far ', style: OkayText.caption),
                    AmountText(d.totalPaisa, style: OkayText.caption),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _GoalCard extends ConsumerWidget {
  const _GoalCard(this.g, {required this.onTap});
  final Goal g;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final calendar = ref.watch(assistantPrefsProvider.select((p) => p.calendar));
    final bridge = ref.watch(hostAppBridgeProvider);
    return OkayCard(
      onTap: onTap,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              ProgressRing(percent: g.percent, size: 64),
              const SizedBox(width: OkaySpacing.lg),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(g.name, style: OkayText.rowTitle),
                    const SizedBox(height: 2),
                    Wrap(
                      children: [
                        AmountText(
                          g.savedPaisa,
                          style: OkayText.subtitle.copyWith(color: OkayColors.text),
                        ),
                        const Text(' of ', style: OkayText.subtitle),
                        AmountText(g.targetPaisa, style: OkayText.subtitle),
                      ],
                    ),
                    Text(switch (g.state) {
                      'done' => 'Reached! Well done.',
                      'overdue' => 'Deadline passed (${formatDate(g.deadline, calendar)})',
                      _ => 'By ${formatDate(g.deadline, calendar)}',
                    }, style: OkayText.caption),
                  ],
                ),
              ),
            ],
          ),
          if (g.state != 'done') ...[
            const SizedBox(height: OkaySpacing.md),
            Wrap(
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                const Text('Needs ', style: OkayText.body),
                AmountText(g.requiredMonthlyPaisa, style: OkayText.amount),
                Text(
                  g.state == 'overdue'
                      ? ' now'
                      : '/month for ${g.monthsLeft} month${g.monthsLeft == 1 ? '' : 's'}',
                  style: OkayText.body,
                ),
              ],
            ),
            const SizedBox(height: OkaySpacing.md),
            FilledButton.icon(
              onPressed: () => bridge.openSmartDeposit(
                prefill: SmartDepositPrefill(
                  goalName: g.name,
                  monthlyAmountPaisa: g.requiredMonthlyPaisa,
                ),
              ),
              icon: const Icon(Icons.savings_outlined, size: 18),
              label: const Text('Automate with Smart Deposit'),
            ),
          ],
        ],
      ),
    );
  }
}

Future<void> showGoalSheet(BuildContext context, {Goal? editing}) => showModalBottomSheet<void>(
  context: context,
  isScrollControlled: true,
  builder: (context) => _GoalSheet(editing: editing),
);

class _GoalSheet extends ConsumerStatefulWidget {
  const _GoalSheet({this.editing});
  final Goal? editing;

  @override
  ConsumerState<_GoalSheet> createState() => _GoalSheetState();
}

class _GoalSheetState extends ConsumerState<_GoalSheet> {
  late final _name = TextEditingController(text: widget.editing?.name ?? '');
  late final _target = TextEditingController(
    text: widget.editing == null ? '' : rupeesInput(widget.editing!.targetPaisa),
  );
  late final _saved = TextEditingController(
    text: widget.editing == null ? '0' : rupeesInput(widget.editing!.savedPaisa),
  );
  late DateTime? _deadline = widget.editing?.deadline;
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _name.dispose();
    _target.dispose();
    _saved.dispose();
    super.dispose();
  }

  Future<void> _pickDeadline() async {
    final now = nepalNow(ref);
    final tomorrow = DateTime(now.year, now.month, now.day + 1);
    final picked = await showDatePicker(
      context: context,
      firstDate: tomorrow,
      lastDate: DateTime(now.year + 30),
      initialDate: _deadline != null && !_deadline!.isBefore(tomorrow)
          ? _deadline!.toLocal()
          : DateTime(now.year + 1, now.month, 1),
    );
    if (picked != null) {
      setState(() => _deadline = DateTime.utc(picked.year, picked.month, picked.day));
    }
  }

  Future<void> _run(Future<void> Function(GoalsController c) action) async {
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await action(ref.read(goalsProvider.notifier));
      if (mounted) Navigator.of(context).pop();
    } on ApiException catch (e) {
      setState(() {
        _saving = false;
        _error = e.message;
      });
    }
  }

  void _save() {
    final name = _name.text.trim();
    final target = parseRupees(_target.text);
    final saved = _saved.text.trim().isEmpty || _saved.text.trim() == '0'
        ? 0
        : parseRupees(_saved.text);
    final problem = name.isEmpty
        ? 'Give the goal a name.'
        : target == null
        ? 'Enter a target above 0.'
        : saved == null
        ? 'Enter how much is saved (or 0).'
        : _deadline == null
        ? 'Pick a deadline.'
        : null;
    if (problem != null) {
      setState(() => _error = problem);
      return;
    }
    final editing = widget.editing;
    _run(
      (c) => editing == null
          ? c.create(name: name, targetPaisa: target!, savedPaisa: saved!, deadline: _deadline!)
          : c.edit(
              editing.id,
              name: name,
              targetPaisa: target,
              savedPaisa: saved,
              deadline: _deadline,
            ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final calendar = ref.watch(assistantPrefsProvider.select((p) => p.calendar));
    final editing = widget.editing;
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
            Text(editing == null ? 'New goal' : 'Edit goal', style: OkayText.sectionTitle),
            const SizedBox(height: OkaySpacing.lg),
            TextField(
              controller: _name,
              maxLength: 120,
              decoration: const InputDecoration(
                hintText: 'Name, e.g. Pokhara trip',
                counterText: '',
              ),
              style: OkayText.body,
            ),
            const SizedBox(height: OkaySpacing.md),
            TextField(
              controller: _target,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(hintText: 'Target (Rs.)'),
              style: OkayText.body,
            ),
            const SizedBox(height: OkaySpacing.md),
            TextField(
              controller: _saved,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(hintText: 'Saved so far (Rs.)'),
              style: OkayText.body,
            ),
            const SizedBox(height: OkaySpacing.md),
            OutlinedButton.icon(
              onPressed: _pickDeadline,
              icon: const Icon(Icons.event_outlined, size: 18),
              label: Text(
                _deadline == null ? 'Pick a deadline' : 'By ${formatDate(_deadline!, calendar)}',
              ),
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
                child: const Text('Delete this goal'),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
