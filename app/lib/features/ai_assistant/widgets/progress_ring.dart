import 'package:flutter/material.dart';

import '../theme/okay_theme.dart';

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
