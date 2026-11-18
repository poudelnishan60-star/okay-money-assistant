import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/money.dart';
import '../../core/privacy.dart';
import '../../theme/okay_theme.dart';
import '../../widgets/widgets.dart';
import '../chat_models.dart';

/// A money-flow (Sankey) diagram: where money came from on the left, the wallet in the
/// middle, where it went on the right. Band thickness is the amount; every node is labelled
/// with its name and amount, and colour says the kind (money in, spent, sent or saved,
/// balance), explained by the legend under it. All figures come from the backend.
///
/// [account]: the Khalti account (money out is "Spent"); otherwise a file ("Money out").
class MoneyFlowDiagram extends ConsumerStatefulWidget {
  const MoneyFlowDiagram(this.flow, {super.key, this.account = false});

  final MoneyFlow flow;
  final bool account;

  @override
  ConsumerState<MoneyFlowDiagram> createState() => _MoneyFlowDiagramState();
}

Color flowColor(String kind) => switch (kind) {
  'in' => OkayColors.positive,
  'out' => OkayColors.accentPink,
  'moved' => OkayChartColors.categorical.first,
  _ => OkayChartColors.other,
};

class _MoneyFlowDiagramState extends ConsumerState<MoneyFlowDiagram>
    with SingleTickerProviderStateMixin {
  late final AnimationController _grow = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  );
  bool _started = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_started) return;
    _started = true;
    if (MediaQuery.disableAnimationsOf(context)) {
      _grow.value = 1;
    } else {
      _grow.forward();
    }
  }

  @override
  void dispose() {
    _grow.dispose();
    super.dispose();
  }

  String _words(String kind) => switch (kind) {
    'in' => 'Money in',
    'out' => widget.account ? 'Spent' : 'Money out',
    'moved' => 'Sent and saved',
    _ => 'Balance',
  };

  @override
  Widget build(BuildContext context) {
    final masked = ref.watch(amountPrivacyProvider.select((p) => p.masked));
    final flow = widget.flow;
    final scaler = MediaQuery.textScalerOf(context);
    // Room for a two-line label (name, amount) next to every node.
    final slot = scaler.scale(12) * 2 * 1.3 + 8;
    final top = scaler.scale(11) * 1.4 + 6; // the "Wallet" caption
    final height = _FlowGeometry(flow: flow, width: 0, top: top, slot: slot).height;
    String npr(int p) => masked ? maskedNpr() : formatNpr(p);
    final kinds = [
      for (final k in ['in', 'out', 'moved', 'balance'])
        if ([...flow.sources, ...flow.uses].any((i) => i.kind == k)) k,
    ];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Semantics(
          label:
              'Money flow. Came from: '
              '${flow.sources.map((i) => '${i.label} ${npr(i.paisa)}').join(', ')}. '
              'Went to: ${flow.uses.map((i) => '${i.label} ${npr(i.paisa)}').join(', ')}.',
          excludeSemantics: true,
          child: SizedBox(
            height: height,
            child: LayoutBuilder(
              builder: (context, c) {
                final g = _FlowGeometry(flow: flow, width: c.maxWidth, top: top, slot: slot);
                return Stack(
                  clipBehavior: Clip.none,
                  children: [
                    Positioned.fill(
                      child: AnimatedBuilder(
                        animation: _grow,
                        builder: (context, _) => CustomPaint(
                          painter: _FlowPainter(g, Curves.easeOutCubic.transform(_grow.value)),
                        ),
                      ),
                    ),
                    Positioned(
                      left: g.walletX - 40,
                      width: 80 + g.walletW,
                      top: math.max(0, g.walletTop - top + 2), // just above the wallet bar
                      child: Text(
                        'Wallet',
                        textAlign: TextAlign.center,
                        style: OkayText.caption.copyWith(fontSize: 11),
                      ),
                    ),
                    for (final (i, item) in flow.sources.indexed)
                      Positioned(
                        left: 0,
                        width: g.leftBarX - 6,
                        top: g.labelTop(g.sourceNodes[i]),
                        child: _Label(item, alignEnd: true),
                      ),
                    for (final (i, item) in flow.uses.indexed)
                      Positioned(
                        left: g.rightBarX + g.barW + 6,
                        right: 0,
                        top: g.labelTop(g.useNodes[i]),
                        child: _Label(item, alignEnd: false),
                      ),
                  ],
                );
              },
            ),
          ),
        ),
        const SizedBox(height: OkaySpacing.md),
        Wrap(
          spacing: OkaySpacing.lg,
          runSpacing: 6,
          children: [
            for (final k in kinds)
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: 10,
                    height: 10,
                    decoration: BoxDecoration(
                      color: flowColor(k),
                      borderRadius: BorderRadius.circular(3),
                    ),
                  ),
                  const SizedBox(width: 6),
                  Flexible(child: Text(_words(k), style: OkayText.caption)),
                ],
              ),
          ],
        ),
      ],
    );
  }
}

class _Label extends StatelessWidget {
  const _Label(this.item, {required this.alignEnd});
  final FlowItem item;
  final bool alignEnd;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: alignEnd ? CrossAxisAlignment.end : CrossAxisAlignment.start,
    children: [
      Text(
        item.label,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        textAlign: alignEnd ? TextAlign.end : TextAlign.start,
        style: OkayText.caption.copyWith(color: OkayColors.text, fontSize: 12),
      ),
      AmountText(
        item.paisa,
        textAlign: alignEnd ? TextAlign.end : TextAlign.start,
        style: OkayText.caption.copyWith(fontSize: 12),
      ),
    ],
  );
}

/// Where every bar, band and label goes. Each node gets its own row, at least as tall as its
/// label, with its bar centred in it, so a label always sits beside its own bar. The wallet
/// bar is shorter than the columns and centred, so the bands funnel into it and out again.
class _FlowGeometry {
  _FlowGeometry({
    required this.flow,
    required double width,
    required double top,
    required this.slot,
  }) {
    leftBarX = width * 0.30;
    rightBarX = width * 0.64 - barW;
    walletX = (leftBarX + barW + rightBarX) / 2 - walletW / 2;
    final total = math.max(1, flow.sources.fold(0, (a, i) => a + i.paisa));
    final rows = math.max(flow.sources.length, flow.uses.length);
    barsTotal = math.max(110.0, rows * slot * 0.6);
    final scale = barsTotal / total;
    final left = _rows(flow.sources, scale);
    final right = _rows(flow.uses, scale);
    final content = [
      left.fold(0.0, (a, r) => a + r),
      right.fold(0.0, (a, r) => a + r),
      barsTotal / 0.8,
    ].reduce(math.max);
    height = top + content + 4;
    sourceNodes = _place(flow.sources, left, scale, top, content);
    useNodes = _place(flow.uses, right, scale, top, content);
    walletTop = top + (content - barsTotal) / 2;
    sourceOnWallet = _onWallet(flow.sources, scale);
    useOnWallet = _onWallet(flow.uses, scale);
  }

  final double barW = 8;
  final double walletW = 10;
  final MoneyFlow flow;
  final double slot;
  late final double height;
  late final double barsTotal;
  late final double walletTop;
  late final double leftBarX;
  late final double rightBarX;
  late final double walletX;
  late final List<(double, double)> sourceNodes; // (top, bottom) of each bar
  late final List<(double, double)> useNodes;
  late final List<(double, double)> sourceOnWallet; // where each band meets the wallet
  late final List<(double, double)> useOnWallet;

  static double _bar(FlowItem i, double scale) => math.max(3.0, i.paisa * scale);

  /// Row heights: the bar plus room around it, never less than a label.
  List<double> _rows(List<FlowItem> items, double scale) => [
    for (final i in items) math.max(slot, _bar(i, scale) + 10),
  ];

  /// Bars centred in their rows; the column centred in the diagram.
  List<(double, double)> _place(
    List<FlowItem> items,
    List<double> rows,
    double scale,
    double top,
    double content,
  ) {
    var y = top + (content - rows.fold(0.0, (a, r) => a + r)) / 2;
    return [
      for (final (k, i) in items.indexed)
        () {
          final h = _bar(i, scale);
          final node = (y + (rows[k] - h) / 2, y + (rows[k] + h) / 2);
          y += rows[k];
          return node;
        }(),
    ];
  }

  /// The wallet carries everything: bands meet it end to end, no gaps.
  List<(double, double)> _onWallet(List<FlowItem> items, double scale) {
    var y = walletTop;
    return [
      for (final i in items)
        () {
          final part = (y, y + i.paisa * scale);
          y = part.$2;
          return part;
        }(),
    ];
  }

  /// A label's top, so its two lines sit centred on the bar.
  double labelTop((double, double) node) => (node.$1 + node.$2) / 2 - (slot - 8) / 2;
}

class _FlowPainter extends CustomPainter {
  _FlowPainter(this.g, this.progress);
  final _FlowGeometry g;
  final double progress;

  Path _band(double x1, (double, double) a, double x2, (double, double) b) {
    final mid = (x1 + x2) / 2;
    return Path()
      ..moveTo(x1, a.$1)
      ..cubicTo(mid, a.$1, mid, b.$1, x2, b.$1)
      ..lineTo(x2, b.$2)
      ..cubicTo(mid, b.$2, mid, a.$2, x1, a.$2)
      ..close();
  }

  @override
  void paint(Canvas canvas, Size size) {
    final flow = g.flow;
    // Bands grow in from the left once.
    canvas.save();
    canvas.clipRect(Rect.fromLTWH(0, 0, size.width * progress, size.height));
    for (final (i, item) in flow.sources.indexed) {
      canvas.drawPath(
        _band(g.leftBarX + g.barW, g.sourceNodes[i], g.walletX, g.sourceOnWallet[i]),
        Paint()..color = flowColor(item.kind).withValues(alpha: 0.4),
      );
    }
    for (final (i, item) in flow.uses.indexed) {
      canvas.drawPath(
        _band(g.walletX + g.walletW, g.useOnWallet[i], g.rightBarX, g.useNodes[i]),
        Paint()..color = flowColor(item.kind).withValues(alpha: 0.4),
      );
    }
    canvas.restore();

    RRect bar(double x, (double, double) y, double w) =>
        RRect.fromRectAndRadius(Rect.fromLTRB(x, y.$1, x + w, y.$2), const Radius.circular(2));
    for (final (i, item) in flow.sources.indexed) {
      canvas.drawRRect(
        bar(g.leftBarX, g.sourceNodes[i], g.barW),
        Paint()..color = flowColor(item.kind),
      );
    }
    for (final (i, item) in flow.uses.indexed) {
      canvas.drawRRect(
        bar(g.rightBarX, g.useNodes[i], g.barW),
        Paint()..color = flowColor(item.kind),
      );
    }
    canvas.drawRRect(
      bar(g.walletX, (g.walletTop, g.walletTop + g.barsTotal), g.walletW),
      Paint()..color = OkayColors.textSecondary,
    );
  }

  @override
  bool shouldRepaint(_FlowPainter old) => old.progress != progress || old.g.flow != g.flow;
}
