import 'dart:math' as math;

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/dates.dart';
import '../../core/money.dart';
import '../../core/preferences.dart';
import '../../core/privacy.dart';
import '../../theme/okay_theme.dart';
import '../../widgets/widgets.dart';
import '../chat_models.dart';
import 'money_flow_view.dart';

/// Charts for a spreadsheet the user added: totals in and out, a 3D pie by type, week by
/// week bars, the biggest payments and the balance line. Every figure was worked out in code
/// by the backend from all the rows; this only draws them. [FileReportCard.sections] says
/// which charts to show (a follow-up like "week by week" gets just that one).
class FileReportView extends ConsumerWidget {
  const FileReportView(this.card, {super.key});
  final FileReportCard card;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final calendar = ref.watch(assistantPrefsProvider.select((p) => p.calendar));
    final sections = <Widget>[
      for (final s in card.sections)
        switch (s) {
          'flow' when card.flow != null => _FlowSection(card.flow!),
          'types' => _TypesPie(card),
          'periods' => _PeriodBars(card),
          'biggest' => _Biggest(card),
          'balance' => _BalanceLine(card),
          _ => const SizedBox.shrink(),
        },
    ];
    final range = card.start == null || card.end == null
        ? null
        : card.start == card.end
        ? formatDate(card.start!, calendar)
        : '${formatShortDate(card.start!, calendar)} – ${formatDate(card.end!, calendar)}';
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(OkaySpacing.lg),
      decoration: BoxDecoration(
        color: OkayColors.surface,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: OkayColors.divider),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  color: OkayColors.iconTileBackground,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Icon(
                  Icons.insert_chart_outlined_rounded,
                  size: 22,
                  color: OkayColors.iconTileForeground,
                ),
              ),
              const SizedBox(width: OkaySpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      card.fileName,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: OkayText.body.copyWith(fontWeight: FontWeight.w600),
                    ),
                    Text(
                      ['${card.rows} row${card.rows == 1 ? '' : 's'}', ?range].join(' · '),
                      style: OkayText.caption,
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: OkaySpacing.lg),
          _Totals(card),
          for (final s in sections) ...[
            const Padding(
              padding: EdgeInsets.symmetric(vertical: OkaySpacing.lg),
              child: Divider(height: 1, color: OkayColors.divider),
            ),
            s,
          ],
          const SizedBox(height: OkaySpacing.md),
          Row(
            children: [
              const Icon(Icons.calculate_outlined, size: 14, color: OkayColors.textSecondary),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  'Worked out in code from all ${card.rows} rows',
                  style: OkayText.caption.copyWith(fontSize: 12),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

// --- shared pieces ----------------------------------------------------------------------

Color _measureColor(String? measure) => switch (measure) {
  'in' => OkayColors.positive,
  'out' => OkayColors.accentPink,
  _ => OkayChartColors.categorical.first,
};

String _measureWords(String? measure) => switch (measure) {
  'in' => 'Money in',
  'out' => 'Money out',
  _ => 'Amounts',
};

String _npr(bool masked, int paisa) => masked ? maskedNpr() : formatNpr(paisa);

/// A share as the backend worked it out: "46%", "7.4%", and "99.8%" (never "100%" for a part).
String _pct(double share) =>
    '${share.toStringAsFixed(share < 10 || (share > 99 && share < 100) ? 1 : 0)}%';

bool _reduceMotion(BuildContext context) => MediaQuery.disableAnimationsOf(context);

/// From 150% text, amounts go under their label instead of beside it.
bool _largeText(BuildContext context) => MediaQuery.textScalerOf(context).scale(10) >= 15;

class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.icon, this.title, {this.trailing});
  final IconData icon;
  final String title;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: OkaySpacing.md),
    child: Row(
      children: [
        Icon(icon, size: 18, color: OkayColors.iconTileForeground),
        const SizedBox(width: OkaySpacing.sm),
        Expanded(
          child: Text(
            title,
            style: OkayText.body.copyWith(fontSize: 15, fontWeight: FontWeight.w600),
          ),
        ),
        ?trailing,
      ],
    ),
  );
}

/// An amount that counts up when it first shows (not with reduced motion).
class _CountUp extends StatelessWidget {
  const _CountUp(this.paisa, {required this.style});
  final int paisa;
  final TextStyle style;

  @override
  Widget build(BuildContext context) => TweenAnimationBuilder<double>(
    tween: Tween(begin: 0, end: paisa.toDouble()),
    duration: _reduceMotion(context) ? Duration.zero : const Duration(milliseconds: 900),
    curve: Curves.easeOutCubic,
    builder: (context, v, _) => AmountText(v.round(), style: style),
  );
}

class _LegendDot extends StatelessWidget {
  const _LegendDot(this.color, this.label);
  final Color color;
  final String label;

  @override
  Widget build(BuildContext context) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      Container(
        width: 10,
        height: 10,
        decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(3)),
      ),
      const SizedBox(width: 6),
      Text(label, style: OkayText.caption),
    ],
  );
}

/// A bar that grows from the left when it first shows (not with reduced motion).
class _GrowBar extends StatelessWidget {
  const _GrowBar({required this.fraction, required this.color, this.height = 10});
  final double fraction;
  final Color color;
  final double height;

  @override
  Widget build(BuildContext context) => TweenAnimationBuilder<double>(
    tween: Tween(begin: 0, end: fraction.clamp(0, 1)),
    duration: _reduceMotion(context) ? Duration.zero : const Duration(milliseconds: 700),
    curve: Curves.easeOutCubic,
    builder: (context, f, _) => LayoutBuilder(
      builder: (context, c) => Stack(
        children: [
          Container(
            height: height,
            decoration: BoxDecoration(
              color: OkayColors.surfaceElevated,
              borderRadius: BorderRadius.circular(height / 2),
            ),
          ),
          Container(
            height: height,
            width: math.max(height, c.maxWidth * f),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(height / 2),
              gradient: LinearGradient(colors: [color.withValues(alpha: 0.65), color]),
            ),
          ),
        ],
      ),
    ),
  );
}

// --- totals -----------------------------------------------------------------------------

class _Totals extends StatelessWidget {
  const _Totals(this.card);
  final FileReportCard card;

  @override
  Widget build(BuildContext context) {
    final inP = card.moneyInPaisa;
    final outP = card.moneyOutPaisa;
    if (inP == null && outP == null) {
      final total = card.totalPaisa;
      if (total == null) return const SizedBox.shrink();
      return _KpiTile(
        label: 'Total',
        paisa: total,
        icon: Icons.functions_rounded,
        color: OkayChartColors.categorical.first,
      );
    }
    final tiles = [
      if (inP != null)
        _KpiTile(
          label: 'Money in',
          paisa: inP,
          icon: Icons.north_rounded,
          color: OkayColors.positive,
        ),
      if (outP != null)
        _KpiTile(
          label: 'Money out',
          paisa: outP,
          icon: Icons.south_rounded,
          color: OkayColors.accentPink,
        ),
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (_largeText(context))
          for (final (i, t) in tiles.indexed) ...[
            if (i > 0) const SizedBox(height: OkaySpacing.sm),
            t,
          ]
        else
          Row(
            children: [
              for (final (i, t) in tiles.indexed) ...[
                if (i > 0) const SizedBox(width: OkaySpacing.sm),
                Expanded(child: t),
              ],
            ],
          ),
        if (inP != null && outP != null && inP + outP > 0) ...[
          const SizedBox(height: OkaySpacing.md),
          _InOutSplit(inPaisa: inP, outPaisa: outP),
        ],
      ],
    );
  }
}

class _KpiTile extends StatelessWidget {
  const _KpiTile({
    required this.label,
    required this.paisa,
    required this.icon,
    required this.color,
  });

  final String label;
  final int paisa;
  final IconData icon;
  final Color color;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(OkaySpacing.md),
    decoration: BoxDecoration(
      color: OkayColors.surfaceElevated,
      borderRadius: BorderRadius.circular(16),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Container(
              width: 22,
              height: 22,
              decoration: BoxDecoration(
                color: color.withValues(alpha: 0.18),
                shape: BoxShape.circle,
              ),
              child: Icon(icon, size: 14, color: color),
            ),
            const SizedBox(width: 6),
            Flexible(child: Text(label, style: OkayText.caption)),
          ],
        ),
        const SizedBox(height: 6),
        FittedBox(
          fit: BoxFit.scaleDown,
          alignment: Alignment.centerLeft,
          child: _CountUp(
            paisa,
            style: OkayText.amount.copyWith(fontSize: 18, fontWeight: FontWeight.w700),
          ),
        ),
      ],
    ),
  );
}

/// Money in against money out as one split bar, with the difference under it.
class _InOutSplit extends ConsumerWidget {
  const _InOutSplit({required this.inPaisa, required this.outPaisa});
  final int inPaisa;
  final int outPaisa;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final net = inPaisa - outPaisa;
    final most = math.max(inPaisa, outPaisa);
    int flex(int v) => v == 0 ? 0 : math.max(1, (v / most * 1000).round());
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Semantics(
          label: 'Money in against money out',
          excludeSemantics: true,
          child: ClipRRect(
            borderRadius: BorderRadius.circular(5),
            child: SizedBox(
              height: 10,
              child: Row(
                children: [
                  if (inPaisa > 0)
                    Expanded(
                      flex: flex(inPaisa),
                      child: const ColoredBox(color: OkayColors.positive),
                    ),
                  if (inPaisa > 0 && outPaisa > 0) const SizedBox(width: 2),
                  if (outPaisa > 0)
                    Expanded(
                      flex: flex(outPaisa),
                      child: const ColoredBox(color: OkayColors.accentPink),
                    ),
                ],
              ),
            ),
          ),
        ),
        const SizedBox(height: 6),
        Wrap(
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            Text('Net ${net >= 0 ? 'in' : 'out'}: ', style: OkayText.caption),
            AmountText(
              net.abs(),
              isDebit: net < 0,
              showArrow: true,
              style: OkayText.caption.copyWith(color: OkayColors.text, fontWeight: FontWeight.w600),
            ),
          ],
        ),
      ],
    );
  }
}

// --- money flow -------------------------------------------------------------------------

class _FlowSection extends StatelessWidget {
  const _FlowSection(this.flow);
  final MoneyFlow flow;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      const _SectionTitle(Icons.account_tree_outlined, 'Where the money came from and went'),
      MoneyFlowDiagram(flow),
    ],
  );
}

// --- pie by type ------------------------------------------------------------------------

class _TypesPie extends ConsumerStatefulWidget {
  const _TypesPie(this.card);
  final FileReportCard card;

  @override
  ConsumerState<_TypesPie> createState() => _TypesPieState();
}

class _TypesPieState extends ConsumerState<_TypesPie> {
  int? _selected;
  bool _showIn = false;

  @override
  Widget build(BuildContext context) {
    final card = widget.card;
    final canSwitch = card.measure == 'out' && card.inByType.length >= 2;
    final showIn = canSwitch && _showIn;
    final slices = showIn ? card.inByType : card.byType;
    final measure = showIn ? 'in' : card.measure;
    final colors = [
      for (final (i, s) in slices.indexed)
        s.isOther || i >= OkayChartColors.categorical.length
            ? OkayChartColors.other
            : OkayChartColors.categorical[i],
    ];
    final selected = _selected != null && _selected! < slices.length ? _selected : null;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _SectionTitle(
          Icons.pie_chart_outline_rounded,
          '${_measureWords(measure)} by ${card.typeColumn ?? 'type'}',
          trailing: canSwitch
              ? _InOutSwitch(
                  showIn: showIn,
                  onChanged: (v) => setState(() {
                    _showIn = v;
                    _selected = null;
                  }),
                )
              : null,
        ),
        Pie3D(
          key: ValueKey(showIn),
          slices: [for (final (i, s) in slices.indexed) Pie3DSlice(s.paisa.toDouble(), colors[i])],
          selected: selected,
          onSelect: (i) => setState(() => _selected = i),
          semanticLabel:
              'Pie chart of ${_measureWords(measure).toLowerCase()} by '
              '${card.typeColumn ?? 'type'}: '
              '${slices.map((s) => '${s.label} ${_pct(s.sharePercent)}').join(', ')}',
        ),
        const SizedBox(height: OkaySpacing.sm),
        for (final (i, s) in slices.indexed)
          _LegendRow(
            color: colors[i],
            slice: s,
            selected: i == selected,
            onTap: () => setState(() => _selected = i == selected ? null : i),
          ),
      ],
    );
  }
}

class _LegendRow extends StatelessWidget {
  const _LegendRow({
    required this.color,
    required this.slice,
    required this.selected,
    required this.onTap,
  });

  final Color color;
  final FileSlice slice;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final share = slice.sharePercent;
    return Semantics(
      selected: selected,
      button: true,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: AnimatedContainer(
          duration: _reduceMotion(context) ? Duration.zero : const Duration(milliseconds: 180),
          constraints: const BoxConstraints(minHeight: 48),
          padding: const EdgeInsets.symmetric(horizontal: OkaySpacing.sm, vertical: 6),
          decoration: BoxDecoration(
            color: selected ? OkayColors.surfaceElevated : Colors.transparent,
            borderRadius: BorderRadius.circular(12),
          ),
          child: Row(
            children: [
              Container(
                width: 12,
                height: 12,
                decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(3)),
              ),
              const SizedBox(width: OkaySpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      slice.label,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: OkayText.body.copyWith(fontSize: 14),
                    ),
                    Text(
                      '${_pct(share)} · '
                      '${slice.rows} row${slice.rows == 1 ? '' : 's'}',
                      style: OkayText.caption.copyWith(fontSize: 12),
                    ),
                    if (_largeText(context))
                      AmountText(slice.paisa, style: OkayText.amount.copyWith(fontSize: 14)),
                  ],
                ),
              ),
              if (!_largeText(context)) ...[
                const SizedBox(width: OkaySpacing.sm),
                AmountText(slice.paisa, style: OkayText.amount.copyWith(fontSize: 14)),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

/// "Out | In" for the pie. Each half is a 48 px tap area.
class _InOutSwitch extends StatelessWidget {
  const _InOutSwitch({required this.showIn, required this.onChanged});
  final bool showIn;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    Widget half(String label, bool isIn) {
      final on = showIn == isIn;
      return Semantics(
        button: true,
        selected: on,
        label: isIn ? 'Show money in' : 'Show money out',
        excludeSemantics: true,
        child: InkWell(
          onTap: () => onChanged(isIn),
          borderRadius: BorderRadius.circular(OkayRadii.pill),
          child: SizedBox(
            height: 48,
            child: Center(
              child: AnimatedContainer(
                duration: _reduceMotion(context)
                    ? Duration.zero
                    : const Duration(milliseconds: 180),
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: on ? OkayColors.surfaceElevated : Colors.transparent,
                  borderRadius: BorderRadius.circular(OkayRadii.pill),
                  border: Border.all(color: on ? OkayColors.chipBorder : Colors.transparent),
                ),
                child: Text(
                  label,
                  style: OkayText.caption.copyWith(
                    color: on ? OkayColors.text : OkayColors.textSecondary,
                    fontWeight: on ? FontWeight.w600 : FontWeight.w400,
                  ),
                ),
              ),
            ),
          ),
        ),
      );
    }

    return Row(mainAxisSize: MainAxisSize.min, children: [half('Out', false), half('In', true)]);
  }
}

// --- week by week -----------------------------------------------------------------------

class _PeriodBars extends ConsumerWidget {
  const _PeriodBars(this.card);
  final FileReportCard card;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final masked = ref.watch(amountPrivacyProvider.select((p) => p.masked));
    final calendar = ref.watch(assistantPrefsProvider.select((p) => p.calendar));
    final periods = card.periods;
    final twoSeries = card.measure == 'out' && periods.any((p) => p.inPaisa > 0);
    final main = _measureColor(card.measure);
    final most = periods.fold(0, (a, p) => math.max(a, math.max(p.paisa, p.inPaisa)));
    final week = card.period == 'week';
    final n = periods.length;
    final rodWidth = n <= 4 ? 16.0 : (n <= 7 ? 11.0 : 7.0);
    final top = periods.reduce((a, b) => b.paisa > a.paisa ? b : a);

    String short(FilePeriod p) =>
        week ? formatShortDate(p.start, calendar) : p.label.split(' ').first; // "Nov 2026" -> "Nov"

    BarChartRodData rod(double toY, Color color) => BarChartRodData(
      toY: toY,
      width: rodWidth,
      borderRadius: const BorderRadius.vertical(top: Radius.circular(4)),
      gradient: LinearGradient(
        begin: Alignment.bottomCenter,
        end: Alignment.topCenter,
        colors: [color.withValues(alpha: 0.55), color],
      ),
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _SectionTitle(Icons.bar_chart_rounded, week ? 'Week by week' : 'Month by month'),
        Wrap(
          spacing: OkaySpacing.lg,
          children: [
            if (twoSeries) const _LegendDot(OkayColors.positive, 'Money in'),
            _LegendDot(main, _measureWords(card.measure)),
          ],
        ),
        const SizedBox(height: OkaySpacing.md),
        Semantics(
          label:
              '${week ? 'Weekly' : 'Monthly'} bar chart of ${_measureWords(card.measure).toLowerCase()}'
              '${twoSeries ? ' and money in' : ''}; highest: ${top.label}',
          excludeSemantics: true,
          child: SizedBox(
            height: 170,
            child: TweenAnimationBuilder<double>(
              tween: Tween(begin: 0, end: 1),
              duration: _reduceMotion(context) ? Duration.zero : const Duration(milliseconds: 800),
              curve: Curves.easeOutCubic,
              builder: (context, t, _) => BarChart(
                duration: Duration.zero,
                BarChartData(
                  maxY: most == 0 ? 1 : most * 1.12,
                  alignment: BarChartAlignment.spaceAround,
                  gridData: FlGridData(
                    drawVerticalLine: false,
                    horizontalInterval: most == 0 ? 1 : most / 3,
                    getDrawingHorizontalLine: (_) =>
                        const FlLine(color: OkayColors.divider, strokeWidth: 1, dashArray: [3, 4]),
                  ),
                  borderData: FlBorderData(
                    show: true,
                    border: const Border(bottom: BorderSide(color: OkayColors.chipBorder)),
                  ),
                  titlesData: FlTitlesData(
                    leftTitles: const AxisTitles(),
                    rightTitles: const AxisTitles(),
                    topTitles: const AxisTitles(),
                    bottomTitles: AxisTitles(
                      sideTitles: SideTitles(
                        showTitles: true,
                        reservedSize: 24,
                        getTitlesWidget: (value, meta) {
                          final i = value.toInt();
                          if (i < 0 || i >= n || (n > 6 && i.isOdd && i != n - 1)) {
                            return const SizedBox.shrink();
                          }
                          return Padding(
                            padding: const EdgeInsets.only(top: 6),
                            child: Text(
                              short(periods[i]),
                              style: OkayText.caption.copyWith(fontSize: 11),
                            ),
                          );
                        },
                      ),
                    ),
                  ),
                  barTouchData: BarTouchData(
                    touchTooltipData: BarTouchTooltipData(
                      getTooltipColor: (_) => OkayColors.surfaceElevated,
                      fitInsideHorizontally: true,
                      fitInsideVertically: true,
                      getTooltipItem: (group, _, rod, rodIndex) {
                        final p = periods[group.x];
                        final isIn = twoSeries && rodIndex == 0;
                        return BarTooltipItem(
                          '${p.label}\n${isIn ? 'Money in' : _measureWords(card.measure)}: '
                          '${_npr(masked, isIn ? p.inPaisa : p.paisa)}',
                          OkayText.caption.copyWith(color: OkayColors.text),
                        );
                      },
                    ),
                  ),
                  barGroups: [
                    for (final (i, p) in periods.indexed)
                      BarChartGroupData(
                        x: i,
                        barsSpace: 3,
                        barRods: [
                          if (twoSeries) rod(p.inPaisa * t, OkayColors.positive),
                          rod(p.paisa * t, main),
                        ],
                      ),
                  ],
                ),
              ),
            ),
          ),
        ),
        if (top.paisa > 0) ...[
          const SizedBox(height: OkaySpacing.md),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Icon(Icons.bolt_rounded, size: 18, color: OkayColors.gold),
              const SizedBox(width: 6),
              Expanded(
                child: Wrap(
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    Text(
                      'Highest ${week ? 'week' : 'month'}: ${top.label}, ',
                      style: OkayText.caption.copyWith(color: OkayColors.text),
                    ),
                    AmountText(
                      top.paisa,
                      style: OkayText.caption.copyWith(
                        color: OkayColors.text,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    Text(
                      ' ${_measureWords(card.measure).toLowerCase()}',
                      style: OkayText.caption.copyWith(color: OkayColors.text),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ],
      ],
    );
  }
}

// --- biggest payments -------------------------------------------------------------------

class _Biggest extends StatelessWidget {
  const _Biggest(this.card);
  final FileReportCard card;

  @override
  Widget build(BuildContext context) {
    final items = card.biggest;
    final most = items.fold(1, (a, s) => math.max(a, s.paisa));
    final color = _measureColor(card.measure);
    final unit = card.measure == 'out' ? 'payment' : 'entry';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _SectionTitle(
          Icons.leaderboard_outlined,
          card.measure == 'out' ? 'Biggest payments' : 'Largest amounts',
        ),
        for (final (i, s) in items.indexed)
          Padding(
            padding: const EdgeInsets.only(bottom: OkaySpacing.md),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(
                      width: 22,
                      child: Text(
                        '${i + 1}',
                        style: OkayText.caption.copyWith(
                          color: i == 0 ? OkayColors.gold : OkayColors.textSecondary,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            s.label,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: OkayText.body.copyWith(fontSize: 14),
                          ),
                          Text(
                            '${s.rows} ${s.rows == 1 ? unit : (unit == 'entry' ? 'entries' : '${unit}s')}'
                            ' · ${_pct(s.sharePercent)}',
                            style: OkayText.caption.copyWith(fontSize: 12),
                          ),
                          if (_largeText(context))
                            AmountText(s.paisa, style: OkayText.amount.copyWith(fontSize: 14)),
                        ],
                      ),
                    ),
                    if (!_largeText(context)) ...[
                      const SizedBox(width: OkaySpacing.sm),
                      AmountText(s.paisa, style: OkayText.amount.copyWith(fontSize: 14)),
                    ],
                  ],
                ),
                const SizedBox(height: 6),
                Padding(
                  padding: const EdgeInsets.only(left: 22),
                  child: _GrowBar(fraction: s.paisa / most, color: color, height: 8),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

// --- balance ----------------------------------------------------------------------------

class _BalanceLine extends ConsumerWidget {
  const _BalanceLine(this.card);
  final FileReportCard card;

  static const _line = Color(0xFF3987E5); // OkayChartColors.categorical[0]

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final masked = ref.watch(amountPrivacyProvider.select((p) => p.masked));
    final calendar = ref.watch(assistantPrefsProvider.select((p) => p.calendar));
    final pts = card.balance;
    final values = [for (final p in pts) p.paisa / 100];
    final lo = values.reduce(math.min);
    final hi = values.reduce(math.max);
    final pad = (hi - lo).abs() < 1 ? 1.0 : (hi - lo) * 0.12;
    final first = pts.first;
    final last = pts.last;
    final change = last.paisa - first.paisa;
    final n = pts.length;
    String when(BalancePoint p) => p.date == null ? '' : formatShortDate(p.date!, calendar);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _SectionTitle(Icons.show_chart_rounded, card.balanceColumn ?? 'Balance'),
        Semantics(
          label:
              'Line chart of the balance, from ${_npr(masked, first.paisa)} to '
              '${_npr(masked, last.paisa)}',
          excludeSemantics: true,
          child: SizedBox(
            height: 150,
            child: TweenAnimationBuilder<double>(
              tween: Tween(begin: 0, end: 1),
              duration: _reduceMotion(context) ? Duration.zero : const Duration(milliseconds: 900),
              curve: Curves.easeOutCubic,
              builder: (context, t, _) => LineChart(
                duration: Duration.zero,
                LineChartData(
                  minX: 0,
                  maxX: math.max(1, n - 1).toDouble(),
                  minY: lo - pad,
                  maxY: hi + pad,
                  clipData: const FlClipData.none(),
                  gridData: FlGridData(
                    drawVerticalLine: false,
                    horizontalInterval: (hi - lo + 2 * pad) / 3,
                    getDrawingHorizontalLine: (_) =>
                        const FlLine(color: OkayColors.divider, strokeWidth: 1, dashArray: [3, 4]),
                  ),
                  borderData: FlBorderData(show: false),
                  extraLinesData: ExtraLinesData(
                    horizontalLines: [
                      if (lo < 0 && hi > 0)
                        HorizontalLine(
                          y: 0,
                          color: OkayColors.textSecondary.withValues(alpha: 0.6),
                          strokeWidth: 1,
                          dashArray: [4, 4],
                          label: HorizontalLineLabel(
                            show: true,
                            alignment: Alignment.topRight,
                            style: OkayText.caption.copyWith(fontSize: 11),
                            labelResolver: (_) => '0',
                          ),
                        ),
                    ],
                  ),
                  titlesData: FlTitlesData(
                    leftTitles: const AxisTitles(),
                    rightTitles: const AxisTitles(),
                    topTitles: const AxisTitles(),
                    bottomTitles: AxisTitles(
                      sideTitles: SideTitles(
                        showTitles: first.date != null,
                        reservedSize: 24,
                        interval: math.max(1, n - 1).toDouble(),
                        getTitlesWidget: (value, meta) {
                          final i = value.round();
                          if (i != 0 && i != n - 1) return const SizedBox.shrink();
                          return SideTitleWidget(
                            meta: meta,
                            fitInside: SideTitleFitInsideData.fromTitleMeta(meta),
                            child: Text(
                              when(pts[i]),
                              style: OkayText.caption.copyWith(fontSize: 11),
                            ),
                          );
                        },
                      ),
                    ),
                  ),
                  lineTouchData: LineTouchData(
                    touchTooltipData: LineTouchTooltipData(
                      getTooltipColor: (_) => OkayColors.surfaceElevated,
                      fitInsideHorizontally: true,
                      fitInsideVertically: true,
                      getTooltipItems: (spots) => [
                        for (final s in spots)
                          LineTooltipItem(
                            [
                              if (pts[s.x.round()].date != null) when(pts[s.x.round()]),
                              _npr(masked, pts[s.x.round()].paisa),
                            ].join('\n'),
                            OkayText.caption.copyWith(color: OkayColors.text),
                          ),
                      ],
                    ),
                  ),
                  lineBarsData: [
                    LineChartBarData(
                      // Drawn left to right as it appears.
                      spots: [
                        for (final (i, v) in values.indexed)
                          if (i <= (n - 1) * t + 0.001) FlSpot(i.toDouble(), v),
                      ],
                      isCurved: true,
                      curveSmoothness: 0.2,
                      preventCurveOverShooting: true,
                      color: _line,
                      barWidth: 2.5,
                      isStrokeCapRound: true,
                      dotData: FlDotData(
                        checkToShowDot: (spot, _) => spot.x == 0 || spot.x == n - 1,
                        getDotPainter: (spot, _, _, _) => FlDotCirclePainter(
                          radius: 4.5,
                          color: _line,
                          strokeWidth: 2,
                          strokeColor: OkayColors.surface,
                        ),
                      ),
                      belowBarData: BarAreaData(
                        show: true,
                        gradient: LinearGradient(
                          begin: Alignment.topCenter,
                          end: Alignment.bottomCenter,
                          colors: [_line.withValues(alpha: 0.35), _line.withValues(alpha: 0)],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
        const SizedBox(height: OkaySpacing.md),
        Wrap(
          crossAxisAlignment: WrapCrossAlignment.center,
          runSpacing: 4,
          children: [
            AmountText(first.paisa, style: OkayText.caption.copyWith(color: OkayColors.text)),
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 4),
              child: Icon(Icons.arrow_forward_rounded, size: 14, color: OkayColors.textSecondary),
            ),
            AmountText(
              last.paisa,
              style: OkayText.caption.copyWith(color: OkayColors.text, fontWeight: FontWeight.w600),
            ),
            if (change != 0) ...[
              const SizedBox(width: OkaySpacing.sm),
              AmountText(
                change.abs(),
                isDebit: change < 0,
                showArrow: true,
                style: OkayText.caption,
              ),
              Text(change < 0 ? ' down' : ' up', style: OkayText.caption),
            ],
          ],
        ),
        if (card.balanceCheck != null) ...[
          const SizedBox(height: OkaySpacing.sm),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(
                card.balanceCheck == 'ok' ? Icons.verified_outlined : Icons.warning_amber_rounded,
                size: 16,
                color: card.balanceCheck == 'ok' ? OkayColors.positive : OkayColors.warning,
              ),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  card.balanceCheck == 'ok'
                      ? 'Checked row by row: it follows money in and out '
                            '(${card.balanceRowsChecked} rows)'
                      : 'Doesn\'t follow money in and out on ${card.balanceRowsOff} of '
                            '${card.balanceRowsChecked} rows checked',
                  style: OkayText.caption,
                ),
              ),
            ],
          ),
        ],
      ],
    );
  }
}
