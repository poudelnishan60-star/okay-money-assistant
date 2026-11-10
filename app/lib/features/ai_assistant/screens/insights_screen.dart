import 'dart:math' as math;

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../chat/message_text.dart';
import '../core/dates.dart';
import '../core/money.dart';
import '../core/preferences.dart';
import '../core/privacy.dart';
import '../data/models.dart';
import '../data/providers.dart';
import '../routes.dart';
import '../theme/okay_theme.dart';
import '../widgets/widgets.dart';

/// Money Insights: month selector, total and change, insight cards, forecast, category donut
/// with its list, daily bars, top merchants. Everything is computed by the backend.
class InsightsScreen extends ConsumerStatefulWidget {
  const InsightsScreen({super.key, this.today});

  /// For tests; defaults to the real date (Nepal time).
  final DateTime? today;

  @override
  ConsumerState<InsightsScreen> createState() => _InsightsScreenState();
}

class _InsightsScreenState extends ConsumerState<InsightsScreen> {
  MonthRef? _month;

  @override
  Widget build(BuildContext context) {
    final calendar = ref.watch(assistantPrefsProvider.select((p) => p.calendar));
    final today = widget.today ?? toNepalTime(DateTime.now());
    final current = MonthRef.containing(today, calendar);
    var month = _month ?? current;
    if (month.calendar != calendar) month = current; // calendar switched in settings
    final isCurrent = month == current;
    final key = (month: isCurrent ? null : month.key, calendar: month.calendarParam);
    final dashboard = ref.watch(dashboardProvider(key));

    return OkayScaffold(
      title: 'Money Insights',
      actions: [
        IconButton(
          tooltip: 'Assistant settings',
          onPressed: () => context.push(OkayRoutes.settings),
          icon: const Icon(Icons.tune_outlined),
        ),
      ],
      body: RefreshIndicator(
        onRefresh: () => ref.refresh(dashboardProvider(key).future),
        child: ListView(
          padding: const EdgeInsets.only(bottom: OkaySpacing.xxl),
          children: [
            const _Shortcuts(),
            const SizedBox(height: OkaySpacing.sm),
            MonthSelector(
              month: month,
              current: current,
              label: dashboard.value?.summary.period.label ?? month.key,
              onChanged: (m) => setState(() => _month = m),
            ),
            AsyncBody(
              value: dashboard,
              onRetry: () => ref.invalidate(dashboardProvider(key)),
              data: (d) => _DashboardBody(d),
            ),
          ],
        ),
      ),
    );
  }
}

class _Shortcuts extends StatelessWidget {
  const _Shortcuts();

  @override
  Widget build(BuildContext context) {
    const items = [
      (Icons.receipt_long_outlined, 'Transactions', OkayRoutes.transactions),
      (Icons.pie_chart_outline_rounded, 'Budgets', OkayRoutes.budgets),
      (Icons.flag_outlined, 'Goals', OkayRoutes.goals),
      (Icons.event_repeat_outlined, 'Bills', OkayRoutes.bills),
      (Icons.chat_bubble_outline_rounded, 'Ask O-Kay', OkayRoutes.chat),
    ];
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.fromLTRB(OkaySpacing.sm, OkaySpacing.sm, OkaySpacing.sm, 0),
      child: Row(
        children: [
          for (final (icon, label, path) in items)
            ServiceIconTile(icon: icon, label: label, onTap: () => context.push(path)),
        ],
      ),
    );
  }
}

class _DashboardBody extends ConsumerWidget {
  const _DashboardBody(this.d);
  final Dashboard d;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final s = d.summary;
    void openTransactions({String? category}) => context.push(
      Uri(
        path: OkayRoutes.transactions,
        queryParameters: {
          'start': apiDate(s.period.start),
          'end': apiDate(s.coveredEnd),
          'spending_only': 'true',
          'category': ?category,
        },
      ).toString(),
    );
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: OkaySpacing.gutter),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _TotalCard(s, onTap: openTransactions),
          for (final h in d.highlights.where((h) => !_shownElsewhere.contains(h.kind)))
            Padding(
              padding: const EdgeInsets.only(top: OkaySpacing.md),
              child: _InsightCard(h),
            ),
          if (d.forecast != null)
            Padding(
              padding: const EdgeInsets.only(top: OkaySpacing.md),
              child: _ForecastCard(d.forecast!),
            ),
          if (s.byCategory.any((c) => c.spentPaisa > 0)) ...[
            const SectionHeader('By category'),
            _CategoryDonut(s, onCategory: (c) => openTransactions(category: c)),
          ],
          if (s.daily.isNotEmpty) ...[const SectionHeader('Day by day'), _DailyBars(s)],
          if (s.topMerchants.isNotEmpty) ...[
            const SectionHeader('Top merchants'),
            _TopMerchants(s.topMerchants),
          ],
        ],
      ),
    );
  }
}

/// Insight kinds the dashboard already shows in its own sections (total card, top merchants,
/// forecast card): no need to repeat them as cards.
const _shownElsewhere = {'month_over_month', 'top_merchant', 'month_end_balance'};

class _TotalCard extends StatelessWidget {
  const _TotalCard(this.s, {required this.onTap});
  final SpendingSummary s;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final pct = s.changePercent;
    final compared = s.comparisonBasis == 'same_days'
        ? 'the same days of ${s.previousPeriod.label}'
        : s.previousPeriod.label;
    return OkayCard(
      onTap: onTap,
      padding: const EdgeInsets.all(OkaySpacing.xl),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(s.inProgress ? 'Spent so far' : 'Spent', style: OkayText.subtitle),
          const SizedBox(height: OkaySpacing.xs),
          AmountText(s.totalPaisa, style: OkayText.bigNumber),
          const SizedBox(height: OkaySpacing.sm),
          if (pct == null)
            Text('Nothing to compare with in $compared', style: OkayText.caption)
          else
            Row(
              children: [
                Icon(
                  pct <= 0 ? Icons.south_rounded : Icons.north_rounded,
                  size: 16,
                  color: pct <= 0 ? OkayColors.positive : OkayColors.accentPink,
                ),
                const SizedBox(width: 4),
                Flexible(
                  child: Text(
                    '${pct.abs().toStringAsFixed(1)}% ${pct <= 0 ? 'less' : 'more'} than $compared',
                    style: OkayText.caption.copyWith(color: OkayColors.text),
                  ),
                ),
              ],
            ),
          const SizedBox(height: OkaySpacing.sm),
          Text(
            '${s.transactionCount} payment${s.transactionCount == 1 ? '' : 's'} · '
            'transfers, savings and income not counted',
            style: OkayText.caption,
          ),
        ],
      ),
    );
  }
}

class _InsightCard extends StatelessWidget {
  const _InsightCard(this.h);
  final Highlight h;

  @override
  Widget build(BuildContext context) {
    final (icon, color) = switch (h.severity) {
      'warning' => (Icons.warning_amber_rounded, OkayColors.warning),
      'positive' => (Icons.thumb_up_alt_outlined, OkayColors.positive),
      _ => (Icons.lightbulb_outline_rounded, OkayColors.gold),
    };
    return Container(
      padding: const EdgeInsets.all(OkaySpacing.lg),
      decoration: BoxDecoration(
        color: OkayColors.surface,
        borderRadius: BorderRadius.circular(OkayRadii.card),
        border: Border.all(color: OkayColors.gold.withValues(alpha: 0.35)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: color, size: 22),
          const SizedBox(width: OkaySpacing.md),
          // Insight text carries amounts: MessageText masks them when the balance is hidden.
          Expanded(child: MessageText(h.message, style: OkayText.body.copyWith(fontSize: 15))),
        ],
      ),
    );
  }
}

class _ForecastCard extends ConsumerWidget {
  const _ForecastCard(this.f);
  final Forecast f;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final calendar = ref.watch(assistantPrefsProvider.select((p) => p.calendar));
    final warn = f.belowThreshold;
    return OkayCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                warn ? Icons.warning_amber_rounded : Icons.trending_up_rounded,
                color: warn ? OkayColors.warning : OkayColors.gold,
                size: 20,
              ),
              const SizedBox(width: OkaySpacing.sm),
              Expanded(
                child: Text(
                  'Balance on ${formatShortDate(f.horizonEnd, calendar)} (forecast)',
                  style: OkayText.subtitle.copyWith(color: OkayColors.text),
                ),
              ),
            ],
          ),
          const SizedBox(height: OkaySpacing.sm),
          AmountText(f.projectedEndPaisa, style: OkayText.bigNumber.copyWith(fontSize: 26)),
          const SizedBox(height: OkaySpacing.xs),
          if (warn)
            Text(
              'May drop below ${formatNpr(f.thresholdPaisa)} around '
              '${formatShortDate(f.firstBelowDate!, calendar)}.',
              style: OkayText.caption.copyWith(color: OkayColors.warning),
            )
          else
            Wrap(
              children: [
                const Text('Lowest point ', style: OkayText.caption),
                AmountText(f.lowestPaisa, style: OkayText.caption),
                Text(' on ${formatShortDate(f.lowestDate, calendar)}', style: OkayText.caption),
              ],
            ),
          const SizedBox(height: OkaySpacing.md),
          for (final item in f.scheduled.take(3))
            Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Row(
                children: [
                  SizedBox(
                    width: 64,
                    child: Text(formatShortDate(item.date, calendar), style: OkayText.caption),
                  ),
                  Expanded(
                    child: Text(
                      item.merchant,
                      style: OkayText.caption,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  AmountText(
                    item.paisa.abs(),
                    isDebit: item.paisa < 0,
                    showArrow: true,
                    style: OkayText.caption.copyWith(color: OkayColors.text),
                  ),
                ],
              ),
            ),
          const SizedBox(height: OkaySpacing.xs),
          // One paragraph, so it wraps word by word (the amount stays maskable).
          Text.rich(
            TextSpan(
              style: OkayText.caption,
              children: [
                const TextSpan(text: 'Based on expected bills and about '),
                WidgetSpan(
                  alignment: PlaceholderAlignment.baseline,
                  baseline: TextBaseline.alphabetic,
                  child: AmountText(f.avgDailySpendPaisa, style: OkayText.caption),
                ),
                const TextSpan(text: ' of everyday spending a day.'),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Category donut + list. Five fixed colours, the rest folded into "Other"; the list carries the
/// exact amounts so colour is never the only way to read it.
class _CategoryDonut extends ConsumerStatefulWidget {
  const _CategoryDonut(this.s, {required this.onCategory});
  final SpendingSummary s;
  final ValueChanged<String> onCategory;

  @override
  ConsumerState<_CategoryDonut> createState() => _CategoryDonutState();
}

class _CategoryDonutState extends ConsumerState<_CategoryDonut> {
  int? _touched;

  @override
  Widget build(BuildContext context) {
    final masked = ref.watch(amountPrivacyProvider.select((p) => p.masked));
    final spent = widget.s.byCategory.where((c) => c.spentPaisa > 0).toList();
    final top = spent.take(OkayChartColors.categorical.length).toList();
    final rest = spent.skip(top.length).toList();
    final slices = <({String name, int paisa, double share, Color color, bool isOther})>[
      for (final (i, c) in top.indexed)
        (
          name: c.category,
          paisa: c.spentPaisa,
          share: c.sharePercent,
          color: OkayChartColors.categorical[i],
          isOther: false,
        ),
      if (rest.isNotEmpty)
        (
          name: 'Other',
          paisa: rest.fold(0, (a, b) => a + b.spentPaisa),
          share: rest.fold(0.0, (a, b) => a + b.sharePercent),
          color: OkayChartColors.other,
          isOther: true,
        ),
    ];
    final touched = _touched == null || _touched! >= slices.length ? null : slices[_touched!];
    return OkayCard(
      child: Column(
        children: [
          Semantics(
            label:
                'Spending by category: '
                '${slices.map((s) => '${s.name} ${s.share.toStringAsFixed(0)}%').join(', ')}',
            excludeSemantics: true,
            child: SizedBox(
              height: 180,
              child: Stack(
                alignment: Alignment.center,
                children: [
                  PieChart(
                    PieChartData(
                      sectionsSpace: 2, // a surface gap between slices
                      centerSpaceRadius: 54,
                      startDegreeOffset: -90,
                      pieTouchData: PieTouchData(
                        touchCallback: (event, response) => setState(
                          () => _touched = event.isInterestedForInteractions
                              ? response?.touchedSection?.touchedSectionIndex
                              : null,
                        ),
                      ),
                      sections: [
                        for (final (i, s) in slices.indexed)
                          PieChartSectionData(
                            value: s.paisa.toDouble(),
                            color: s.color,
                            radius: i == _touched ? 30 : 24,
                            showTitle: false,
                          ),
                      ],
                    ),
                  ),
                  Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(touched?.name ?? 'Total', style: OkayText.caption),
                      Text(
                        masked ? maskedNpr() : formatNpr(touched?.paisa ?? widget.s.totalPaisa),
                        style: OkayText.amount,
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: OkaySpacing.md),
          for (final s in slices)
            InkWell(
              onTap: s.isOther ? null : () => widget.onCategory(s.name),
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 8),
                child: Row(
                  children: [
                    Container(
                      width: 12,
                      height: 12,
                      decoration: BoxDecoration(
                        color: s.color,
                        borderRadius: BorderRadius.circular(3),
                      ),
                    ),
                    const SizedBox(width: OkaySpacing.md),
                    Expanded(child: Text(s.name, style: OkayText.body.copyWith(fontSize: 15))),
                    Text('${s.share.toStringAsFixed(0)}%  ', style: OkayText.caption),
                    AmountText(s.paisa, style: OkayText.amount.copyWith(fontSize: 15)),
                    if (!s.isOther)
                      const Icon(
                        Icons.chevron_right_rounded,
                        size: 18,
                        color: OkayColors.textSecondary,
                      ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// Daily spending: one hue, thin bars, rounded tops on the baseline; tap a bar for the figure.
class _DailyBars extends ConsumerWidget {
  const _DailyBars(this.s);
  final SpendingSummary s;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final masked = ref.watch(amountPrivacyProvider.select((p) => p.masked));
    final calendar = ref.watch(assistantPrefsProvider.select((p) => p.calendar));
    final maxPaisa = s.daily.fold(0, (a, d) => math.max(a, d.paisa));
    final top = s.daily.isEmpty ? null : s.daily.reduce((a, b) => b.paisa > a.paisa ? b : a);
    return OkayCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Semantics(
            label: top == null || top.paisa == 0
                ? 'No spending this period'
                : 'Daily spending; highest on ${formatShortDate(top.date, calendar)}',
            excludeSemantics: true,
            child: SizedBox(
              height: 150,
              child: BarChart(
                BarChartData(
                  maxY: maxPaisa == 0 ? 1 : maxPaisa * 1.1,
                  alignment: BarChartAlignment.spaceBetween,
                  gridData: const FlGridData(show: false),
                  borderData: FlBorderData(
                    show: true,
                    border: const Border(bottom: BorderSide(color: OkayColors.divider)),
                  ),
                  titlesData: FlTitlesData(
                    leftTitles: const AxisTitles(),
                    rightTitles: const AxisTitles(),
                    topTitles: const AxisTitles(),
                    bottomTitles: AxisTitles(
                      sideTitles: SideTitles(
                        showTitles: true,
                        reservedSize: 22,
                        getTitlesWidget: (value, meta) {
                          final i = value.toInt();
                          if (i < 0 || i >= s.daily.length) return const SizedBox.shrink();
                          final last = i == s.daily.length - 1;
                          if (i % 7 != 0 && !last) return const SizedBox.shrink();
                          final day = s.daily[i].date;
                          final label = calendar == CalendarSystem.bs
                              ? formatShortDate(day, calendar).split(' ').first
                              : '${day.day}';
                          return Padding(
                            padding: const EdgeInsets.only(top: 4),
                            child: Text(label, style: OkayText.caption),
                          );
                        },
                      ),
                    ),
                  ),
                  barTouchData: BarTouchData(
                    touchTooltipData: BarTouchTooltipData(
                      getTooltipColor: (_) => OkayColors.surfaceElevated,
                      getTooltipItem: (group, _, rod, _) => BarTooltipItem(
                        '${formatShortDate(s.daily[group.x].date, calendar)}\n'
                        '${masked ? maskedNpr() : formatNpr(s.daily[group.x].paisa)}',
                        OkayText.caption.copyWith(color: OkayColors.text),
                      ),
                    ),
                  ),
                  barGroups: [
                    for (final (i, d) in s.daily.indexed)
                      BarChartGroupData(
                        x: i,
                        barRods: [
                          BarChartRodData(
                            toY: d.paisa.toDouble(),
                            width: s.daily.length > 20 ? 5 : 9,
                            color: OkayChartColors.single,
                            borderRadius: const BorderRadius.vertical(top: Radius.circular(3)),
                          ),
                        ],
                      ),
                  ],
                ),
              ),
            ),
          ),
          if (top != null && top.paisa > 0) ...[
            const SizedBox(height: OkaySpacing.sm),
            Wrap(
              children: [
                Text('Highest: ${formatShortDate(top.date, calendar)}, ', style: OkayText.caption),
                AmountText(top.paisa, style: OkayText.caption),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

class _TopMerchants extends StatelessWidget {
  const _TopMerchants(this.merchants);
  final List<MerchantSpend> merchants;

  @override
  Widget build(BuildContext context) {
    return OkayCard(
      padding: const EdgeInsets.symmetric(horizontal: OkaySpacing.lg, vertical: OkaySpacing.sm),
      child: Column(
        children: [
          for (final (i, m) in merchants.indexed)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 10),
              child: Row(
                children: [
                  SizedBox(width: 22, child: Text('${i + 1}', style: OkayText.caption)),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(m.merchant, style: OkayText.body.copyWith(fontSize: 15)),
                        Text(
                          '${m.category} · ${m.count} payment${m.count == 1 ? '' : 's'}',
                          style: OkayText.caption,
                        ),
                      ],
                    ),
                  ),
                  AmountText(m.spentPaisa, style: OkayText.amount.copyWith(fontSize: 15)),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
