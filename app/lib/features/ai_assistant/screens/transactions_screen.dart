import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/api_client.dart';
import '../core/dates.dart';
import '../core/preferences.dart';
import '../data/models.dart';
import '../data/providers.dart';
import '../data/repositories.dart';
import '../theme/okay_theme.dart';
import '../widgets/widgets.dart';

/// Transactions grouped by day with closing balances. Opens with the filters of a chat link
/// ("View 12 transactions ->") or the 30-day chip.
class TransactionsScreen extends ConsumerStatefulWidget {
  const TransactionsScreen({super.key, this.initial = const TxnQuery(period: '30d')});

  final TxnQuery initial;

  @override
  ConsumerState<TransactionsScreen> createState() => _TransactionsScreenState();
}

class _TransactionsScreenState extends ConsumerState<TransactionsScreen> {
  late TxnQuery _query = widget.initial.period == null && widget.initial.start == null
      ? widget.initial.withRange(period: '30d')
      : widget.initial;

  PeriodChoice get _chip => switch (_query.period) {
    '7d' => PeriodChoice.days7,
    '14d' => PeriodChoice.days14,
    '30d' => PeriodChoice.days30,
    'this_month' => PeriodChoice.thisMonth,
    _ => PeriodChoice.custom,
  };

  Future<void> _pick(PeriodChoice choice) async {
    if (choice != PeriodChoice.custom) {
      setState(() => _query = _query.withRange(period: choice.apiValue));
      return;
    }
    final now = toNepalTime(DateTime.now());
    final today = DateTime(now.year, now.month, now.day);
    final range = await showDateRangePicker(
      context: context,
      firstDate: today.subtract(const Duration(days: 365)),
      lastDate: today,
      initialDateRange: _query.start != null && _query.end != null
          ? DateTimeRange(start: _query.start!.toLocal(), end: _query.end!.toLocal())
          : null,
    );
    if (range == null) return;
    setState(() {
      _query = _query.withRange(
        start: DateTime.utc(range.start.year, range.start.month, range.start.day),
        end: DateTime.utc(range.end.year, range.end.month, range.end.day),
      );
    });
  }

  String _filterLabel() {
    final parts = <String>[
      ?_query.category,
      if (_query.merchant != null) '“${_query.merchant}”',
      if (_query.type != null) _query.type!.replaceAll('_', ' '),
      if (_query.direction == 'debit') 'money out',
      if (_query.direction == 'credit') 'money in',
      if (_query.spendingOnly) 'spending only',
    ];
    return parts.join(' · ');
  }

  @override
  Widget build(BuildContext context) {
    final calendar = ref.watch(assistantPrefsProvider.select((p) => p.calendar));
    final list = ref.watch(transactionsProvider(_query));
    return OkayScaffold(
      title: 'Transactions',
      body: Column(
        children: [
          const SizedBox(height: OkaySpacing.sm),
          PeriodChips(selected: _chip, onChanged: _pick),
          if (_query.hasExtraFilters)
            Padding(
              padding: const EdgeInsets.fromLTRB(
                OkaySpacing.gutter,
                OkaySpacing.sm,
                OkaySpacing.gutter,
                0,
              ),
              child: Align(
                alignment: Alignment.centerLeft,
                child: InputChip(
                  label: Text(
                    _filterLabel(),
                    style: OkayText.caption.copyWith(color: OkayColors.text),
                  ),
                  onDeleted: () => setState(() => _query = _query.rangeOnly),
                  deleteButtonTooltipMessage: 'Clear filters',
                  side: const BorderSide(color: OkayColors.chipSelected),
                  shape: const StadiumBorder(),
                  backgroundColor: OkayColors.background,
                ),
              ),
            ),
          Expanded(
            child: AsyncBody(
              value: list,
              onRetry: () => ref.invalidate(transactionsProvider(_query)),
              data: (state) => _TxnList(
                state: state,
                calendar: calendar,
                onMore: () => ref.read(transactionsProvider(_query).notifier).loadMore(),
                onOpen: (t) => showTransactionSheet(
                  context,
                  t,
                  onChanged: () {
                    ref.invalidate(transactionsProvider);
                    ref.invalidate(dashboardProvider);
                  },
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _TxnList extends StatelessWidget {
  const _TxnList({
    required this.state,
    required this.calendar,
    required this.onMore,
    required this.onOpen,
  });

  final TxnListState state;
  final CalendarSystem calendar;
  final VoidCallback onMore;
  final ValueChanged<Txn> onOpen;

  @override
  Widget build(BuildContext context) {
    final page = state.page;
    if (state.items.isEmpty) {
      return const EmptyView(
        title: 'No transactions',
        message: 'Try a longer period or clear the filters.',
      );
    }
    // Flatten into: summary, then for each day a header followed by its rows.
    final entries = <Object>[];
    DateTime? day;
    for (final t in state.items) {
      if (t.day != day) {
        day = t.day;
        entries.add(t.day); // newest first, so the first row of a day holds its closing balance
      }
      entries.add(t);
    }
    final closing = <DateTime, int?>{};
    for (final t in state.items) {
      closing.putIfAbsent(t.day, () => t.balanceAfterPaisa);
    }
    return ListView.builder(
      itemCount: entries.length + 2,
      itemBuilder: (context, i) {
        if (i == 0) {
          return Padding(
            padding: const EdgeInsets.fromLTRB(
              OkaySpacing.gutter,
              OkaySpacing.md,
              OkaySpacing.gutter,
              0,
            ),
            child: Wrap(
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                Text(
                  '${page.total} transaction${page.total == 1 ? '' : 's'} · out ',
                  style: OkayText.caption,
                ),
                AmountText(
                  page.totalDebitPaisa,
                  style: OkayText.caption.copyWith(color: OkayColors.text),
                ),
                const Text(' · in ', style: OkayText.caption),
                AmountText(
                  page.totalCreditPaisa,
                  style: OkayText.caption.copyWith(color: OkayColors.text),
                ),
              ],
            ),
          );
        }
        if (i == entries.length + 1) {
          if (!state.hasMore) return const SizedBox(height: OkaySpacing.xxl);
          return Padding(
            padding: const EdgeInsets.all(OkaySpacing.lg),
            child: Center(
              child: state.loadingMore
                  ? const CircularProgressIndicator()
                  : OutlinedButton(onPressed: onMore, child: const Text('Load more')),
            ),
          );
        }
        final e = entries[i - 1];
        if (e is DateTime) {
          return DateGroupHeader(date: e, closingBalancePaisa: closing[e], calendar: calendar);
        }
        final t = e as Txn;
        final visual = transactionVisual(t.type, t.service);
        return TransactionRow(
          icon: visual.icon,
          title: visual.title,
          merchant: t.merchant,
          reference: t.reference,
          nepalTime: t.occurredAt,
          amountPaisa: t.amountPaisa,
          isDebit: t.isDebit,
          onTap: () => onOpen(t),
        );
      },
    );
  }
}

/// Transaction detail: category (editable), merchant, note, "apply to all from this merchant".
Future<void> showTransactionSheet(BuildContext context, Txn t, {required VoidCallback onChanged}) =>
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (context) => _TransactionSheet(t, onChanged: onChanged),
    );

class _TransactionSheet extends ConsumerStatefulWidget {
  const _TransactionSheet(this.t, {required this.onChanged});
  final Txn t;
  final VoidCallback onChanged;

  @override
  ConsumerState<_TransactionSheet> createState() => _TransactionSheetState();
}

class _TransactionSheetState extends ConsumerState<_TransactionSheet> {
  late String _category = widget.t.category;
  late String? _sub = widget.t.subcategory;
  bool _applyAll = false;
  bool _saving = false;
  String? _error;

  bool get _changed => _category != widget.t.category || _sub != widget.t.subcategory;

  Future<void> _save() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final n = await ref
          .read(transactionsRepositoryProvider)
          .recategorize(widget.t.id, _category, subcategory: _sub, applyToMerchant: _applyAll);
      widget.onChanged();
      if (!mounted) return;
      final messenger = ScaffoldMessenger.of(context);
      Navigator.of(context).pop();
      messenger.showSnackBar(
        SnackBar(
          content: Text(
            n == 1 ? 'Category updated' : 'Updated $n transactions from ${widget.t.merchant}',
          ),
        ),
      );
    } on ApiException catch (e) {
      setState(() {
        _saving = false;
        _error = e.message;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = widget.t;
    final calendar = ref.watch(assistantPrefsProvider.select((p) => p.calendar));
    final categories = ref.watch(categoriesProvider).value ?? const <CategoryInfo>[];
    final subs =
        categories.where((c) => c.name == _category).firstOrNull?.subcategories ?? const <String>[];
    final visual = transactionVisual(t.type, t.service);
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
            Text(visual.title, style: OkayText.subtitle),
            const SizedBox(height: OkaySpacing.xs),
            AmountText(
              t.amountPaisa,
              isDebit: t.isDebit,
              showArrow: true,
              style: OkayText.bigNumber.copyWith(fontSize: 28),
            ),
            const SizedBox(height: OkaySpacing.lg),
            _Line('Merchant', t.merchant),
            _Line('When', '${formatDate(t.occurredAt, calendar)} · ${formatTime(t.occurredAt)}'),
            if (t.reference != null) _Line('Reference', t.reference!),
            // A note typed by a person: shown as plain text, never interpreted.
            if (t.remarks != null && t.remarks!.isNotEmpty) _Line('Note', t.remarks!),
            const SizedBox(height: OkaySpacing.lg),
            const Text('Category', style: OkayText.subtitle),
            const SizedBox(height: OkaySpacing.sm),
            DropdownButtonFormField<String>(
              initialValue: _category,
              isExpanded: true,
              decoration: const InputDecoration(),
              items: [
                for (final c
                    in categories.isEmpty ? [CategoryInfo(_category, const [], true)] : categories)
                  DropdownMenuItem(value: c.name, child: Text(c.name)),
              ],
              onChanged: (v) => setState(() {
                _category = v ?? _category;
                _sub = null;
              }),
            ),
            if (subs.isNotEmpty) ...[
              const SizedBox(height: OkaySpacing.md),
              Wrap(
                spacing: OkaySpacing.sm,
                runSpacing: OkaySpacing.sm,
                children: [
                  for (final s in subs)
                    PillChip(
                      label: s,
                      selected: _sub == s,
                      onTap: () => setState(() => _sub = _sub == s ? null : s),
                    ),
                ],
              ),
            ],
            const SizedBox(height: OkaySpacing.sm),
            CheckboxListTile(
              value: _applyAll,
              onChanged: (v) => setState(() => _applyAll = v ?? false),
              contentPadding: EdgeInsets.zero,
              controlAffinity: ListTileControlAffinity.leading,
              title: Text('Apply to all from ${t.merchant}', style: OkayText.body),
              subtitle: const Text('Past and future payments', style: OkayText.caption),
            ),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(bottom: OkaySpacing.sm),
                child: Text(_error!, style: OkayText.caption.copyWith(color: OkayColors.warning)),
              ),
            FilledButton(
              onPressed: (_changed || _applyAll) && !_saving ? _save : null,
              child: _saving
                  ? const SizedBox.square(
                      dimension: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text('Save'),
            ),
          ],
        ),
      ),
    );
  }
}

class _Line extends StatelessWidget {
  const _Line(this.label, this.value);
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: OkaySpacing.sm),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(width: 92, child: Text(label, style: OkayText.caption)),
        Expanded(child: Text(value, style: OkayText.body.copyWith(fontSize: 15))),
      ],
    ),
  );
}
