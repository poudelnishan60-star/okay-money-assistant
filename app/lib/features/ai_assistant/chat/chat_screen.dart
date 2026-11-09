import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../host/host_app_bridge.dart';
import '../theme/okay_theme.dart';
import '../widgets/widgets.dart';
import 'cards/card_views.dart';
import 'chat_controller.dart';
import 'chat_models.dart';
import 'message_text.dart';

/// The O-Kay chat: streamed answers, rich cards, follow-up chips, confirmations.
class ChatScreen extends ConsumerStatefulWidget {
  const ChatScreen({super.key});

  @override
  ConsumerState<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends ConsumerState<ChatScreen> {
  final _input = TextEditingController();
  final _focus = FocusNode();

  @override
  void initState() {
    super.initState();
    Future.microtask(() => ref.read(chatControllerProvider.notifier).loadHistory());
    _input.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _input.dispose();
    _focus.dispose();
    super.dispose();
  }

  void _send([String? text]) {
    final value = (text ?? _input.text).trim();
    if (value.isEmpty) return;
    _input.clear();
    ref.read(chatControllerProvider.notifier).send(value);
  }

  Future<void> _confirmClear() async {
    final ok = await showModalBottomSheet<bool>(
      context: context,
      builder: (context) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(OkaySpacing.xl, 0, OkaySpacing.xl, OkaySpacing.xl),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text('Clear this chat?', style: OkayText.sectionTitle),
              const SizedBox(height: OkaySpacing.xs),
              const Text(
                'Your messages with O-Kay are deleted. Your money data is not touched.',
                style: OkayText.subtitle,
              ),
              const SizedBox(height: OkaySpacing.xl),
              FilledButton(
                onPressed: () => Navigator.of(context).pop(true),
                child: const Text('Clear chat'),
              ),
              const SizedBox(height: OkaySpacing.sm),
              OutlinedButton(
                onPressed: () => Navigator.of(context).pop(false),
                child: const Text('Keep it'),
              ),
            ],
          ),
        ),
      ),
    );
    if (ok ?? false) await ref.read(chatControllerProvider.notifier).clear();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(chatControllerProvider);
    final messages = state.messages;
    return Scaffold(
      backgroundColor: OkayColors.chatBackground,
      appBar: AppBar(
        backgroundColor: OkayColors.chatBackground,
        titleSpacing: 0,
        title: const Row(
          children: [
            MascotSlot(size: 36),
            SizedBox(width: OkaySpacing.md),
            Flexible(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('O-Kay', style: OkayText.rowTitle, overflow: TextOverflow.ellipsis),
                  Text(
                    'Your money assistant',
                    style: OkayText.caption,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
          ],
        ),
        actions: [
          if (messages.isNotEmpty)
            IconButton(
              tooltip: 'Clear chat',
              onPressed: state.sending ? null : _confirmClear,
              icon: const Icon(Icons.delete_outline),
            ),
        ],
      ),
      body: SafeArea(
        top: false,
        child: Column(
          children: [
            Expanded(
              child: messages.isEmpty
                  ? _EmptyState(onPick: _send, loading: !state.historyLoaded)
                  : ListView.builder(
                      reverse: true,
                      padding: const EdgeInsets.fromLTRB(
                        OkaySpacing.gutter,
                        OkaySpacing.lg,
                        OkaySpacing.gutter,
                        OkaySpacing.sm,
                      ),
                      itemCount: messages.length,
                      itemBuilder: (context, i) {
                        final index = messages.length - 1 - i;
                        return _MessageView(
                          message: messages[index],
                          index: index,
                          onRetry: () => ref.read(chatControllerProvider.notifier).retry(index),
                        );
                      },
                    ),
            ),
            _ChipRow(chips: state.chips, enabled: !state.sending, onPick: _send),
            _Composer(
              controller: _input,
              focusNode: _focus,
              canSend: !state.sending && _input.text.trim().isNotEmpty,
              onSend: _send,
            ),
          ],
        ),
      ),
    );
  }
}

// --- empty state ------------------------------------------------------------------------

class _EmptyState extends StatelessWidget {
  const _EmptyState({required this.onPick, required this.loading});

  final ValueChanged<String> onPick;
  final bool loading;

  static const _quick = [
    (Icons.insights_outlined, 'My spending', 'How much did I spend this month?'),
    (Icons.pie_chart_outline_rounded, 'Budgets', 'Show my budgets'),
    (Icons.receipt_long_outlined, 'Upcoming bills', 'Which bills are due soon?'),
    (Icons.flag_outlined, 'Savings goals', 'How are my savings goals?'),
  ];

  @override
  Widget build(BuildContext context) {
    if (loading) return const LoadingView();
    return SingleChildScrollView(
      padding: const EdgeInsets.all(OkaySpacing.gutter),
      child: Column(
        children: [
          const SizedBox(height: OkaySpacing.xl),
          const MascotSlot(size: 112, glow: true),
          const SizedBox(height: OkaySpacing.xl),
          const Text('Start Chatting with O-Kay', style: OkayText.sectionTitle),
          const SizedBox(height: OkaySpacing.xs),
          const Text(
            'Ask about your spending, budgets, bills and goals,\nin English, नेपाली or Romanized Nepali.',
            style: OkayText.subtitle,
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: OkaySpacing.xl),
          // Two rows of two cards. Each card is as tall as its content (large system text
          // sizes would overflow a fixed grid cell); IntrinsicHeight keeps a row even.
          for (var row = 0; row < 2; row++)
            Padding(
              padding: const EdgeInsets.only(bottom: OkaySpacing.md),
              child: IntrinsicHeight(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Expanded(
                      child: _QuickCard(item: _quick[row * 2], onPick: onPick),
                    ),
                    const SizedBox(width: OkaySpacing.md),
                    Expanded(
                      child: _QuickCard(item: _quick[row * 2 + 1], onPick: onPick),
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

class _QuickCard extends StatelessWidget {
  const _QuickCard({required this.item, required this.onPick});

  final (IconData, String, String) item;
  final ValueChanged<String> onPick;

  @override
  Widget build(BuildContext context) {
    final (icon, label, prompt) = item;
    return OkayCard(
      padding: const EdgeInsets.all(OkaySpacing.lg),
      onTap: () => onPick(prompt),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: OkayColors.iconTileBackground,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(icon, color: OkayColors.iconTileForeground, size: 22),
          ),
          const SizedBox(height: OkaySpacing.lg),
          Text(label, style: OkayText.body.copyWith(fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}

// --- messages ---------------------------------------------------------------------------

const _toolWords = {
  'get_spending_summary': 'Adding up your spending…',
  'get_transactions': 'Looking through your transactions…',
  'get_budgets': 'Checking your budgets…',
  'upsert_budget': 'Preparing your budget…',
  'get_goals': 'Checking your goals…',
  'upsert_goal': 'Preparing your goal…',
  'get_recurring_payments': 'Finding your bills…',
  'get_balance_forecast': 'Forecasting your balance…',
  'search_help_articles': 'Searching help articles…',
  'open_app_flow': 'Getting that ready…',
};

class _MessageView extends ConsumerWidget {
  const _MessageView({required this.message, required this.index, required this.onRetry});

  final ChatMessage message;
  final int index;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final maxWidth = MediaQuery.sizeOf(context).width * 0.8;
    if (message.isUser) {
      return Padding(
        padding: const EdgeInsets.only(bottom: OkaySpacing.md),
        child: Align(
          alignment: Alignment.centerRight,
          child: ConstrainedBox(
            constraints: BoxConstraints(maxWidth: maxWidth),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              decoration: const BoxDecoration(
                color: OkayColors.userBubble,
                borderRadius: BorderRadius.only(
                  topLeft: Radius.circular(OkayRadii.bubble),
                  topRight: Radius.circular(OkayRadii.bubble),
                  bottomLeft: Radius.circular(OkayRadii.bubble),
                  bottomRight: Radius.circular(6),
                ),
              ),
              child: Text(message.text, style: OkayText.body),
            ),
          ),
        ),
      );
    }

    final bridge = ref.watch(hostAppBridgeProvider);
    final controller = ref.read(chatControllerProvider.notifier);
    final waiting = message.streaming && message.text.isEmpty;
    final retryable = {'busy', 'rate_limited', 'network', 'unavailable'}.contains(message.error);
    return Padding(
      padding: const EdgeInsets.only(bottom: OkaySpacing.lg),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Padding(padding: EdgeInsets.only(top: 2), child: MascotSlot(size: 28)),
          const SizedBox(width: OkaySpacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  decoration: const BoxDecoration(
                    color: OkayColors.assistantBubble,
                    borderRadius: BorderRadius.only(
                      topLeft: Radius.circular(6),
                      topRight: Radius.circular(OkayRadii.bubble),
                      bottomLeft: Radius.circular(OkayRadii.bubble),
                      bottomRight: Radius.circular(OkayRadii.bubble),
                    ),
                  ),
                  child: waiting
                      ? _Thinking(label: _toolWords[message.toolStatus])
                      : MessageText(message.text),
                ),
                if (message.toolStatus != null && !waiting)
                  Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: Text(_toolWords[message.toolStatus] ?? '…', style: OkayText.caption),
                  ),
                for (final (i, card) in message.cards.indexed)
                  Padding(
                    padding: const EdgeInsets.only(top: OkaySpacing.sm),
                    child: ChatCardView(card: card, messageIndex: index, cardIndex: i),
                  ),
                if (!message.streaming)
                  Padding(
                    padding: const EdgeInsets.only(top: OkaySpacing.sm),
                    child: Wrap(
                      spacing: OkaySpacing.sm,
                      runSpacing: OkaySpacing.sm,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: [
                        for (final s in message.suggestions.where((s) => s.isFeature))
                          PillChip(
                            label: s.text,
                            icon: s.feature == 'smart_deposit'
                                ? Icons.savings_outlined
                                : Icons.autorenew,
                            onTap: () => s.feature == 'smart_deposit'
                                ? bridge.openSmartDeposit()
                                : bridge.openAutopay(),
                          ),
                        if (retryable)
                          PillChip(label: 'Try again', icon: Icons.refresh, onTap: onRetry),
                        if (message.id != null && message.error == null) ...[
                          _Thumb(
                            up: true,
                            selected: message.feedback == 'up',
                            onTap: () => controller.setFeedback(index, 'up'),
                          ),
                          _Thumb(
                            up: false,
                            selected: message.feedback == 'down',
                            onTap: () => controller.setFeedback(index, 'down'),
                          ),
                        ],
                      ],
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Thinking extends StatefulWidget {
  const _Thinking({this.label});
  final String? label;

  @override
  State<_Thinking> createState() => _ThinkingState();
}

class _ThinkingState extends State<_Thinking> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1200),
  )..repeat();

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: widget.label ?? 'O-Kay is typing',
      liveRegion: true,
      excludeSemantics: true,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          AnimatedBuilder(
            animation: _c,
            builder: (context, _) => Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                for (var i = 0; i < 3; i++)
                  Container(
                    margin: const EdgeInsets.symmetric(horizontal: 2),
                    width: 7,
                    height: 7,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: OkayColors.textSecondary.withValues(
                        alpha: 0.35 + 0.65 * (((_c.value * 3 - i) % 3) < 1 ? 1 : 0),
                      ),
                    ),
                  ),
              ],
            ),
          ),
          if (widget.label != null) ...[
            const SizedBox(width: OkaySpacing.sm),
            Flexible(child: Text(widget.label!, style: OkayText.caption)),
          ],
        ],
      ),
    );
  }
}

class _Thumb extends StatelessWidget {
  const _Thumb({required this.up, required this.selected, required this.onTap});
  final bool up;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final icon = up
        ? (selected ? Icons.thumb_up : Icons.thumb_up_outlined)
        : (selected ? Icons.thumb_down : Icons.thumb_down_outlined);
    return IconButton(
      tooltip: up ? 'Helpful' : 'Not helpful',
      isSelected: selected,
      onPressed: onTap,
      visualDensity: VisualDensity.compact,
      icon: Icon(icon, size: 18, color: selected ? OkayColors.gold : OkayColors.textSecondary),
    );
  }
}

// --- chips and input --------------------------------------------------------------------

class _ChipRow extends StatelessWidget {
  const _ChipRow({required this.chips, required this.enabled, required this.onPick});
  final List<Suggestion> chips;
  final bool enabled;
  final ValueChanged<String> onPick;

  @override
  Widget build(BuildContext context) {
    if (chips.isEmpty) return const SizedBox.shrink();
    // A handful of chips: a plain scrolling row builds them all (no lazy off-screen items).
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.symmetric(horizontal: OkaySpacing.gutter, vertical: 6),
      child: Row(
        children: [
          for (final (i, chip) in chips.indexed) ...[
            if (i > 0) const SizedBox(width: OkaySpacing.sm),
            Opacity(
              opacity: enabled ? 1 : 0.5,
              child: PillChip(label: chip.text, onTap: enabled ? () => onPick(chip.text) : null),
            ),
          ],
        ],
      ),
    );
  }
}

class _Composer extends StatelessWidget {
  const _Composer({
    required this.controller,
    required this.focusNode,
    required this.canSend,
    required this.onSend,
  });

  final TextEditingController controller;
  final FocusNode focusNode;
  final bool canSend;
  final VoidCallback onSend;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        OkaySpacing.gutter,
        OkaySpacing.xs,
        OkaySpacing.gutter,
        OkaySpacing.md,
      ),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: controller,
              focusNode: focusNode,
              minLines: 1,
              maxLines: 4,
              maxLength: 1000,
              maxLengthEnforcement: MaxLengthEnforcement.enforced,
              textInputAction: TextInputAction.send,
              onSubmitted: (_) => canSend ? onSend() : null,
              style: OkayText.body,
              decoration: const InputDecoration(hintText: 'Ask O-Kay', counterText: ''),
            ),
          ),
          const SizedBox(width: OkaySpacing.sm),
          Semantics(
            button: true,
            label: 'Send',
            excludeSemantics: true,
            child: Material(
              color: canSend ? OkayColors.primary : OkayColors.surfaceElevated,
              shape: const CircleBorder(),
              child: InkWell(
                customBorder: const CircleBorder(),
                onTap: canSend ? onSend : null,
                child: const SizedBox.square(
                  dimension: 48,
                  child: Icon(Icons.arrow_upward_rounded, color: OkayColors.text),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
