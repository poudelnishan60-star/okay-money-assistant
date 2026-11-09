import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/money.dart';
import '../core/privacy.dart';
import '../theme/okay_theme.dart';

/// "Rs. 1,270", "Rs 1,140.67", "रु. १,२७०" as written in answers.
final amountPattern = RegExp(r'(?:Rs\.?|रु\.?)\s?[\d,०-९]+(?:\.[\d०-९]+)?');
final _bold = RegExp(r'\*\*(.+?)\*\*');

/// Answer text: renders **bold**, and masks every amount while the user's balance is hidden
/// (tap to reveal), so privacy holds inside the AI's prose too, not only in cards.
class MessageText extends ConsumerWidget {
  const MessageText(this.text, {super.key, this.style = OkayText.body});

  final String text;
  final TextStyle style;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final masked = ref.watch(amountPrivacyProvider.select((p) => p.masked));
    final spans = <TextSpan>[];
    var last = 0;
    String show(String s) => masked ? s.replaceAll(amountPattern, maskedNpr()) : s;
    for (final m in _bold.allMatches(text)) {
      if (m.start > last) spans.add(TextSpan(text: show(text.substring(last, m.start))));
      spans.add(
        TextSpan(
          text: show(m[1]!),
          style: const TextStyle(fontWeight: FontWeight.w700),
        ),
      );
      last = m.end;
    }
    if (last < text.length) spans.add(TextSpan(text: show(text.substring(last))));
    final rich = Text.rich(TextSpan(style: style, children: spans));
    if (!masked || !amountPattern.hasMatch(text)) return rich;
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => ref.read(amountPrivacyProvider.notifier).reveal(),
      child: Semantics(hint: 'Amounts hidden. Double tap to show.', child: rich),
    );
  }
}
