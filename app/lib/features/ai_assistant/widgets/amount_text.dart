import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/money.dart';
import '../core/privacy.dart';
import '../theme/okay_theme.dart';

/// Every amount on the assistant screens goes through this widget, so balance privacy is
/// applied everywhere: masked as 'Rs. ••••' until the user taps it.
class AmountText extends ConsumerWidget {
  const AmountText(
    this.paisa, {
    super.key,
    this.style = OkayText.amount,
    this.isDebit,
    this.showArrow = false,
    this.alwaysDecimals = false,
    this.textAlign,
  });

  final int paisa;
  final TextStyle style;

  /// When set with [showArrow], shows a pink down-arrow (debit) or green up-arrow (credit).
  final bool? isDebit;
  final bool showArrow;
  final bool alwaysDecimals;
  final TextAlign? textAlign;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final masked = ref.watch(amountPrivacyProvider.select((p) => p.masked));
    final text = masked ? maskedNpr() : formatNpr(paisa, alwaysDecimals: alwaysDecimals);
    Widget child = Text(text, style: style, textAlign: textAlign, maxLines: 1);
    if (showArrow && isDebit != null) {
      child = Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          DirectionArrow(isDebit: isDebit!, size: (style.fontSize ?? 16) + 2),
          const SizedBox(width: 2),
          Flexible(child: child),
        ],
      );
    }
    if (!masked) return child;
    return Semantics(
      label: 'Amount hidden. Double tap to show amounts.',
      button: true,
      excludeSemantics: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () => ref.read(amountPrivacyProvider.notifier).reveal(),
        child: child,
      ),
    );
  }
}

class DirectionArrow extends StatelessWidget {
  const DirectionArrow({super.key, required this.isDebit, this.size = 18});

  final bool isDebit;
  final double size;

  @override
  Widget build(BuildContext context) {
    return Icon(
      isDebit ? Icons.south_rounded : Icons.north_rounded,
      size: size,
      color: isDebit ? OkayColors.accentPink : OkayColors.positive,
      semanticLabel: isDebit ? 'Debit' : 'Credit',
    );
  }
}
