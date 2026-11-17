import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';

import '../theme/okay_theme.dart';

/// One slice of a [Pie3D].
@immutable
class Pie3DSlice {
  const Pie3DSlice(this.value, this.color);
  final double value;
  final Color color;
}

/// A pie drawn tilted, with depth. The tilt bends how big a slice looks, so it always goes
/// with a legend that gives each slice's exact share and amount (see the chat's file card).
///
/// Slices start at 12 o'clock and run clockwise, in the given order. Tap a slice to lift it
/// out ([onSelect] gets its index, or null when tapped again). Sweeps in once when shown,
/// unless the platform asks for reduced motion.
class Pie3D extends StatefulWidget {
  const Pie3D({
    super.key,
    required this.slices,
    required this.semanticLabel,
    this.selected,
    this.onSelect,
    this.height = 170,
  });

  final List<Pie3DSlice> slices;
  final String semanticLabel;
  final int? selected;
  final ValueChanged<int?>? onSelect;
  final double height;

  @override
  State<Pie3D> createState() => _Pie3DState();
}

class _Pie3DState extends State<Pie3D> with TickerProviderStateMixin {
  late final AnimationController _sweep = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  );
  late final AnimationController _lift = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 220),
  );
  int? _lifted;
  bool _started = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_started) {
      _started = true;
      if (MediaQuery.disableAnimationsOf(context)) {
        _sweep.value = 1;
      } else {
        _sweep.forward();
      }
    }
    _syncLift();
  }

  @override
  void didUpdateWidget(Pie3D old) {
    super.didUpdateWidget(old);
    _syncLift();
  }

  void _syncLift() {
    final reduce = MediaQuery.disableAnimationsOf(context);
    final target = widget.selected == null ? 0.0 : 1.0;
    if (widget.selected != null) _lifted = widget.selected;
    if (reduce) {
      _lift.value = target;
    } else {
      _lift.animateTo(target);
    }
  }

  @override
  void dispose() {
    _sweep.dispose();
    _lift.dispose();
    super.dispose();
  }

  void _tap(Offset at, Size size) {
    final onSelect = widget.onSelect;
    if (onSelect == null) return;
    final hit = _PieGeometry(size).sliceAt(at, widget.slices, 1);
    onSelect(hit == null || hit == widget.selected ? null : hit);
  }

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: widget.semanticLabel,
      image: true,
      excludeSemantics: true,
      child: SizedBox(
        height: widget.height,
        child: LayoutBuilder(
          builder: (context, c) {
            final size = Size(c.maxWidth, widget.height);
            return GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTapUp: (d) => _tap(d.localPosition, size),
              child: AnimatedBuilder(
                animation: Listenable.merge([_sweep, _lift]),
                builder: (context, _) => CustomPaint(
                  size: size,
                  painter: _Pie3DPainter(
                    slices: widget.slices,
                    progress: Curves.easeOutCubic.transform(_sweep.value),
                    lifted: _lifted,
                    lift: Curves.easeOut.transform(_lift.value),
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }
}

/// Where the pie sits in its box: the top face is an ellipse, the walls hang [depth] below.
class _PieGeometry {
  _PieGeometry(this.size) {
    depth = (size.height * 0.13).clamp(10, 26);
    const pad = 12.0; // room for a lifted slice and the shadow
    rx = math.min(size.width / 2 - pad, (size.height - depth - 2 * pad) / (2 * tilt));
    ry = rx * tilt;
    center = Offset(size.width / 2, pad + ry);
  }

  static const tilt = 0.56; // ry / rx
  static const start = -math.pi / 2; // 12 o'clock
  final Size size;
  late final double depth;
  late final double rx;
  late final double ry;
  late final Offset center;

  Rect top(Offset shift) => Rect.fromCenter(center: center + shift, width: rx * 2, height: ry * 2);

  Rect bottom(Offset shift) => top(shift).shift(Offset(0, depth));

  Offset rim(double angle, Offset shift, {bool low = false}) =>
      center + shift + Offset(rx * math.cos(angle), ry * math.sin(angle) + (low ? depth : 0));

  /// Which slice a point is on (top face or wall), or null.
  int? sliceAt(Offset p, List<Pie3DSlice> slices, double progress) {
    final total = slices.fold(0.0, (a, s) => a + math.max(0, s.value));
    if (total <= 0) return null;
    for (final dy in [0.0, depth]) {
      final x = (p.dx - center.dx) / rx;
      final y = (p.dy - center.dy - dy) / ry;
      if (x * x + y * y > 1.05) continue;
      var a = math.atan2(y, x) - start;
      while (a < 0) {
        a += 2 * math.pi;
      }
      var from = 0.0;
      for (final (i, s) in slices.indexed) {
        final sweep = math.max(0, s.value) / total * 2 * math.pi * progress;
        if (a >= from && a < from + sweep) return i;
        from += sweep;
      }
    }
    return null;
  }
}

class _Pie3DPainter extends CustomPainter {
  _Pie3DPainter({
    required this.slices,
    required this.progress,
    required this.lifted,
    required this.lift,
  });

  final List<Pie3DSlice> slices;
  final double progress;
  final int? lifted;
  final double lift;

  static Color _shade(Color c, double amount) => Color.lerp(c, Colors.black, amount)!;

  @override
  void paint(Canvas canvas, Size size) {
    final g = _PieGeometry(size);
    final total = slices.fold(0.0, (a, s) => a + math.max(0, s.value));
    if (total <= 0 || g.rx <= 0) return;

    // Soft shadow under the pie.
    canvas.drawOval(
      g.bottom(Offset.zero).inflate(4).shift(const Offset(0, 4)),
      Paint()
        ..color = Colors.black.withValues(alpha: 0.45)
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 10),
    );

    final parts = <({int i, double from, double sweep, Offset shift, Color color})>[];
    var from = _PieGeometry.start;
    for (final (i, s) in slices.indexed) {
      final sweep = math.max(0, s.value) / total * 2 * math.pi * progress;
      final mid = from + sweep / 2;
      final out = i == lifted ? 10 * lift : 0.0;
      final shift = Offset(math.cos(mid) * out, math.sin(mid) * out * _PieGeometry.tilt);
      parts.add((i: i, from: from, sweep: sweep, shift: shift, color: s.color));
      from += sweep;
    }

    final gap = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5
      ..color = OkayColors.surface;
    final bounds = g.top(Offset.zero).inflate(12);

    // Walls first (only the front half shows), then the lifted slice's cut faces, then the
    // top faces; the lifted slice last, so it sits above its neighbours.
    final order = [...parts.where((p) => p.i != lifted), ...parts.where((p) => p.i == lifted)];
    for (final p in order) {
      final a0 = math.max(p.from, 0.0);
      final a1 = math.min(p.from + p.sweep, math.pi);
      if (a1 <= a0) continue;
      final wall = Path()
        ..arcTo(g.top(p.shift), a0, a1 - a0, true)
        ..lineTo(g.rim(a1, p.shift, low: true).dx, g.rim(a1, p.shift, low: true).dy)
        ..arcTo(g.bottom(p.shift), a1, a0 - a1, false)
        ..close();
      canvas.drawPath(
        wall,
        Paint()
          ..shader = ui.Gradient.linear(
            bounds.centerLeft,
            bounds.centerRight,
            [_shade(p.color, 0.62), _shade(p.color, 0.28), _shade(p.color, 0.55)],
            const [0, 0.45, 1],
          ),
      );
      canvas.drawPath(wall, gap);
    }

    final up = lifted;
    if (up != null && lift > 0 && up < parts.length) {
      final p = parts[up];
      for (final a in [p.from, p.from + p.sweep]) {
        final face = Path()
          ..moveTo(g.center.dx + p.shift.dx, g.center.dy + p.shift.dy)
          ..lineTo(g.rim(a, p.shift).dx, g.rim(a, p.shift).dy)
          ..lineTo(g.rim(a, p.shift, low: true).dx, g.rim(a, p.shift, low: true).dy)
          ..lineTo(g.center.dx + p.shift.dx, g.center.dy + p.shift.dy + g.depth)
          ..close();
        canvas.drawPath(face, Paint()..color = _shade(p.color, 0.45));
      }
    }

    for (final p in order) {
      if (p.sweep <= 0) continue;
      final c = g.center + p.shift;
      final top = Path()..moveTo(c.dx, c.dy);
      if (p.sweep >= 2 * math.pi - 1e-6) {
        top.addOval(g.top(p.shift));
      } else {
        top
          ..arcTo(g.top(p.shift), p.from, p.sweep, false)
          ..close();
      }
      canvas.drawPath(top, Paint()..color = p.color);
      // A soft light from the top left, the same for every slice.
      canvas.drawPath(
        top,
        Paint()
          ..shader = ui.Gradient.radial(g.center + Offset(-g.rx * 0.35, -g.ry * 0.55), g.rx * 1.3, [
            Colors.white.withValues(alpha: 0.22),
            Colors.white.withValues(alpha: 0),
          ]),
      );
      canvas.drawPath(top, gap);
      if (p.i == lifted && lift > 0) {
        canvas.drawPath(
          top,
          Paint()
            ..style = PaintingStyle.stroke
            ..strokeWidth = 2
            ..color = OkayColors.text.withValues(alpha: 0.9 * lift),
        );
      }
    }
  }

  @override
  bool shouldRepaint(_Pie3DPainter old) =>
      old.progress != progress ||
      old.lift != lift ||
      old.lifted != lifted ||
      !_sameSlices(old.slices, slices);

  static bool _sameSlices(List<Pie3DSlice> a, List<Pie3DSlice> b) {
    if (a.length != b.length) return false;
    for (var i = 0; i < a.length; i++) {
      if (a[i].value != b[i].value || a[i].color != b[i].color) return false;
    }
    return true;
  }
}
