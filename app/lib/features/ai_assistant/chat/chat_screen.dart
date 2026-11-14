import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../data/providers.dart';
import '../host/host_app_bridge.dart';
import '../routes.dart';
import '../theme/okay_theme.dart';
import '../widgets/widgets.dart';
import 'attachments.dart';
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
    if (value.isEmpty && ref.read(chatControllerProvider).pending.isEmpty) return;
    _input.clear();
    ref.read(chatControllerProvider.notifier).send(value);
  }

  Future<void> _addFiles() async {
    final choice = await showModalBottomSheet<_FileChoice>(
      context: context,
      isScrollControlled: true, // as tall as it needs (large text), scrolls if taller
      builder: (context) => const _AddFilesSheet(),
    );
    if (choice == null || !mounted) return;
    final source = ref.read(fileSourceProvider);
    final messenger = ScaffoldMessenger.of(context);
    List<PickedFile> files;
    try {
      files = choice == _FileChoice.photo
          ? await source.pickPhotos()
          : await source.pickDocuments();
    } on Exception {
      messenger.showSnackBar(const SnackBar(content: Text("Couldn't open your files.")));
      return;
    }
    if (files.isEmpty || !mounted) return;
    final problems = ref.read(chatControllerProvider.notifier).addFiles(files);
    if (problems.isNotEmpty) {
      messenger.showSnackBar(SnackBar(content: Text(problems.join('\n'))));
    }
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
    return TabTitle(
      title: 'Chat',
      child: Scaffold(
        backgroundColor: OkayColors.chatBackground,
        // Minimal chrome, as in the Khalti app: back, the name, and the mascot.
        appBar: AppBar(
          backgroundColor: OkayColors.chatBackground,
          // On the website the chat is the front page: no back arrow, so keep the gutter.
          titleSpacing: (ModalRoute.of(context)?.canPop ?? false) ? 0 : OkaySpacing.gutter,
          title: Text('O-Kay', style: OkayText.rowTitle.copyWith(fontWeight: FontWeight.w600)),
          shape: const Border(bottom: BorderSide(color: OkayChatColors.headerDivider)),
          actions: [
            _MascotMenu(canClear: messages.isNotEmpty && !state.sending, onClear: _confirmClear),
            const SizedBox(width: OkaySpacing.sm),
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
                canSend:
                    !state.sending && (_input.text.trim().isNotEmpty || state.pending.isNotEmpty),
                onSend: _send,
                pending: state.pending,
                onAdd: state.sending ? null : _addFiles,
                onRemove: ref.read(chatControllerProvider.notifier).removePending,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// --- empty state ------------------------------------------------------------------------

enum _Menu { insights, alerts, settings, clear }

/// The mascot in the header is the one control there: it opens the way to the assistant's
/// other screens. Every item has an icon and a label; the badge and the Alerts row show how
/// many alerts are unread; clearing the chat sits apart, in red.
class _MascotMenu extends ConsumerWidget {
  const _MascotMenu({required this.canClear, required this.onClear});

  final bool canClear;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final unread = ref.watch(unreadAlertsProvider);
    return PopupMenuButton<_Menu>(
      tooltip: unread == 0 ? 'Menu' : 'Menu, $unread unread alerts',
      position: PopupMenuPosition.under,
      color: OkayColors.surfaceElevated,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(16))),
      onSelected: (choice) {
        switch (choice) {
          case _Menu.insights:
            context.push(OkayRoutes.insights);
          case _Menu.alerts:
            context.push(OkayRoutes.alerts);
          case _Menu.settings:
            context.push(OkayRoutes.settings);
          case _Menu.clear:
            onClear();
        }
      },
      itemBuilder: (context) => [
        const PopupMenuItem(
          value: _Menu.insights,
          child: _MenuRow(Icons.insights_outlined, 'Money Insights'),
        ),
        PopupMenuItem(
          value: _Menu.alerts,
          child: _MenuRow(Icons.notifications_none_outlined, 'Alerts', count: unread),
        ),
        const PopupMenuItem(
          value: _Menu.settings,
          child: _MenuRow(Icons.tune_rounded, 'Assistant settings'),
        ),
        const PopupMenuDivider(),
        PopupMenuItem(
          value: _Menu.clear,
          enabled: canClear,
          child: _MenuRow(
            Icons.delete_outline_rounded,
            'Clear chat',
            color: canClear ? OkayChatColors.dangerText : Theme.of(context).disabledColor,
          ),
        ),
      ],
      child: SizedBox.square(
        dimension: OkaySizes.minTouchTarget,
        child: Center(
          child: Badge(
            isLabelVisible: unread > 0,
            label: Text('$unread'),
            backgroundColor: OkayColors.primary,
            textColor: OkayColors.text,
            child: const MascotSlot(size: 36, decorative: true),
          ),
        ),
      ),
    );
  }
}

class _MenuRow extends StatelessWidget {
  const _MenuRow(this.icon, this.label, {this.count = 0, this.color = OkayColors.text});

  final IconData icon;
  final String label;
  final int count;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 22, color: color),
        const SizedBox(width: OkaySpacing.md),
        // Wraps instead of overflowing at very large text sizes.
        Flexible(
          child: Text(label, style: OkayText.body.copyWith(color: color)),
        ),
        if (count > 0) ...[
          const SizedBox(width: OkaySpacing.md),
          Badge(
            label: Text('$count'),
            backgroundColor: OkayColors.primary,
            textColor: OkayColors.text,
          ),
        ],
      ],
    );
  }
}

/// Shown while the chat history loads. The demo's free server sleeps when nobody is using
/// it and takes up to a minute to wake, so after a few seconds this says what is going on.
class _Connecting extends StatefulWidget {
  const _Connecting();

  @override
  State<_Connecting> createState() => _ConnectingState();
}

class _ConnectingState extends State<_Connecting> {
  static const _patience = Duration(seconds: 4);
  Timer? _timer;
  bool _slow = false;

  @override
  void initState() {
    super.initState();
    _timer = Timer(_patience, () => setState(() => _slow = true));
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(OkaySpacing.xl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const CircularProgressIndicator(),
            if (_slow) ...[
              const SizedBox(height: OkaySpacing.lg),
              const Text('Waking O-Kay up…', style: OkayText.rowTitle),
              const SizedBox(height: OkaySpacing.xs),
              const Text(
                'The demo server sleeps when nobody is using it. This can take up to a minute.',
                style: OkayText.subtitle,
                textAlign: TextAlign.center,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

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

  /// The Khalti app's 2x2 grid: two 124 pt cards, centred (its 15 pt gap rounded to 16).
  static const _gridWidth = 264.0;
  static const _gap = OkaySpacing.lg;

  @override
  Widget build(BuildContext context) {
    if (loading) return const _Connecting();
    // Larger system text gets a wider grid (up to the screen), so labels wrap less.
    final gridWidth = MediaQuery.textScalerOf(context).scale(_gridWidth).clamp(_gridWidth, 360.0);
    return LayoutBuilder(
      builder: (context, constraints) => SingleChildScrollView(
        padding: const EdgeInsets.symmetric(
          horizontal: OkaySpacing.gutter,
          vertical: OkaySpacing.lg,
        ),
        // Centred in the space above the chips when it fits; scrolls when it does not.
        child: ConstrainedBox(
          constraints: BoxConstraints(minHeight: constraints.maxHeight - 2 * OkaySpacing.lg),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              // The title below names it, so the picture itself is not announced.
              const MascotSlot(size: 168, decorative: true),
              const SizedBox(height: OkaySpacing.xl),
              Semantics(
                header: true,
                child: Text(
                  'Start Chatting with O-Kay',
                  style: OkayText.sectionTitle.copyWith(fontSize: 22, fontWeight: FontWeight.w600),
                  textAlign: TextAlign.center,
                ),
              ),
              const SizedBox(height: OkaySpacing.xxl),
              ConstrainedBox(
                constraints: BoxConstraints(maxWidth: gridWidth),
                child: Column(
                  children: [
                    // Each card is as tall as its content (large text wraps); a row stays even.
                    for (var row = 0; row < 2; row++) ...[
                      if (row > 0) const SizedBox(height: _gap),
                      IntrinsicHeight(
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            Expanded(
                              child: _QuickCard(item: _quick[row * 2], onPick: onPick),
                            ),
                            const SizedBox(width: _gap),
                            Expanded(
                              child: _QuickCard(item: _quick[row * 2 + 1], onPick: onPick),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              // The block sits a little above centre, as in the Khalti app.
              const SizedBox(height: OkaySpacing.xl),
            ],
          ),
        ),
      ),
    );
  }
}

/// A quick-start card: icon tile above a centred label.
class _QuickCard extends StatelessWidget {
  const _QuickCard({required this.item, required this.onPick});

  final (IconData, String, String) item;
  final ValueChanged<String> onPick;

  @override
  Widget build(BuildContext context) {
    final (icon, label, prompt) = item;
    return Material(
      color: OkayChatColors.quickCard,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.all(Radius.circular(12)),
        side: BorderSide(color: OkayChatColors.quickCardBorder),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => onPick(prompt),
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 92),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(OkaySpacing.sm, 12, OkaySpacing.sm, 14),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Container(
                  width: 36,
                  height: 36,
                  decoration: BoxDecoration(
                    color: OkayChatColors.quickIconTile,
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: OkayChatColors.quickIconTileBorder),
                  ),
                  child: Icon(icon, color: OkayChatColors.quickIcon, size: 20),
                ),
                const SizedBox(height: 10),
                Text(
                  label,
                  style: OkayText.subtitle.copyWith(color: OkayColors.text),
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          ),
        ),
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
  'read_attachment': 'Reading your file…',
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
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                mainAxisSize: MainAxisSize.min,
                children: [
                  for (final (i, a) in message.attachments.indexed) ...[
                    if (i > 0) const SizedBox(height: OkaySpacing.sm),
                    _SentFile(a),
                  ],
                  if (message.attachments.isNotEmpty && message.text.isNotEmpty)
                    const SizedBox(height: OkaySpacing.sm),
                  if (message.text.isNotEmpty) Text(message.text, style: OkayText.body),
                ],
              ),
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
          const Padding(
            padding: EdgeInsets.only(top: 2),
            child: MascotSlot(size: 28, decorative: true),
          ),
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
      padding: const EdgeInsets.symmetric(horizontal: OkaySpacing.gutter, vertical: 2),
      child: Row(
        children: [
          for (final (i, chip) in chips.indexed) ...[
            if (i > 0) const SizedBox(width: OkaySpacing.sm),
            Opacity(
              opacity: enabled ? 1 : 0.5,
              child: _SuggestionChip(chip: chip, onTap: enabled ? () => onPick(chip.text) : null),
            ),
          ],
        ],
      ),
    );
  }
}

const _starterChipIcons = {
  'This month vs last': Icons.compare_arrows_rounded,
  'Where did my money go?': Icons.pie_chart_outline_rounded,
  'Set a food budget': Icons.restaurant_outlined,
};

IconData _chipIcon(Suggestion chip) => switch (chip.feature) {
  'smart_deposit' => Icons.savings_outlined,
  'autopay' => Icons.autorenew_rounded,
  _ => _starterChipIcons[chip.text] ?? Icons.auto_awesome_outlined,
};

/// A suggestion above the input: a pill with a small light icon tile, as in the Khalti app.
class _SuggestionChip extends StatelessWidget {
  const _SuggestionChip({required this.chip, required this.onTap});

  final Suggestion chip;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    // The pill is 40 px tall; the 4 px above and below it also take the tap (48 px in all).
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: OkaySpacing.xs),
        child: _pill(),
      ),
    );
  }

  Widget _pill() {
    return Material(
      color: OkayColors.chatBackground,
      shape: const StadiumBorder(side: BorderSide(color: OkayChatColors.chipBorder)),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 40),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(10, 6, 14, 6),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 22,
                  height: 22,
                  decoration: BoxDecoration(
                    color: OkayChatColors.chipIconTile,
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Icon(_chipIcon(chip), size: 14, color: OkayChatColors.chipIcon),
                ),
                const SizedBox(width: OkaySpacing.sm),
                Text(
                  chip.text,
                  style: OkayText.subtitle.copyWith(
                    color: OkayColors.text,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// The input: one pill holding the text field and, inside it on the right, the send button.
class _Composer extends StatelessWidget {
  const _Composer({
    required this.controller,
    required this.focusNode,
    required this.canSend,
    required this.onSend,
    required this.pending,
    required this.onAdd,
    required this.onRemove,
  });

  final TextEditingController controller;
  final FocusNode focusNode;
  final bool canSend;
  final VoidCallback onSend;
  final List<ChatAttachment> pending;
  final VoidCallback? onAdd;
  final ValueChanged<int> onRemove;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        OkaySpacing.gutter,
        OkaySpacing.xs,
        OkaySpacing.gutter,
        OkaySpacing.md,
      ),
      // The border brightens while the field has focus (there is no other focus ring).
      child: ListenableBuilder(
        listenable: focusNode,
        builder: (context, child) => DecoratedBox(
          decoration: ShapeDecoration(
            color: OkayChatColors.inputFill,
            shape: RoundedRectangleBorder(
              borderRadius: const BorderRadius.all(Radius.circular(28)),
              side: BorderSide(
                color: focusNode.hasFocus ? OkayColors.textSecondary : OkayChatColors.inputBorder,
              ),
            ),
          ),
          child: child,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Wraps onto a second line (at most 3 files) so every remove button stays in view.
            if (pending.isNotEmpty)
              Padding(
                padding: const EdgeInsets.fromLTRB(
                  OkaySpacing.md,
                  OkaySpacing.md,
                  OkaySpacing.md,
                  0,
                ),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: Wrap(
                    spacing: OkaySpacing.sm,
                    runSpacing: OkaySpacing.sm,
                    children: [
                      for (final (i, a) in pending.indexed)
                        _PendingFile(a, onRemove: () => onRemove(i)),
                    ],
                  ),
                ),
              ),
            Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Padding(
                  padding: const EdgeInsets.only(left: 2, bottom: 2, top: 2),
                  child: IconButton(
                    tooltip: 'Add files and photos',
                    onPressed: onAdd,
                    constraints: const BoxConstraints.tightFor(
                      width: OkaySizes.minTouchTarget,
                      height: OkaySizes.minTouchTarget,
                    ),
                    icon: const Icon(Icons.add_rounded, color: OkayColors.textSecondary, size: 26),
                  ),
                ),
                Expanded(
                  child: Semantics(
                    label: 'Message to O-Kay',
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
                      decoration: const InputDecoration(
                        hintText: 'Ask O-Kay',
                        hintStyle: TextStyle(color: OkayColors.textSecondary, fontSize: 16),
                        counterText: '',
                        filled: false,
                        border: InputBorder.none,
                        enabledBorder: InputBorder.none,
                        focusedBorder: InputBorder.none,
                        contentPadding: EdgeInsets.fromLTRB(4, 15, 4, 15),
                      ),
                    ),
                  ),
                ),
                // A 40 px circle with a 48 px tap area.
                Padding(
                  padding: const EdgeInsets.all(2),
                  child: Semantics(
                    button: true,
                    enabled: canSend,
                    label: 'Send',
                    excludeSemantics: true,
                    child: InkWell(
                      customBorder: const CircleBorder(),
                      onTap: canSend ? onSend : null,
                      child: SizedBox.square(
                        dimension: OkaySizes.minTouchTarget,
                        child: Center(
                          child: AnimatedContainer(
                            duration: MediaQuery.disableAnimationsOf(context)
                                ? Duration.zero
                                : const Duration(milliseconds: 150),
                            width: 40,
                            height: 40,
                            decoration: BoxDecoration(
                              color: canSend ? OkayColors.primary : OkayChatColors.sendIdle,
                              shape: BoxShape.circle,
                            ),
                            child: Icon(
                              Icons.arrow_forward_rounded,
                              size: 22,
                              color: OkayColors.text.withValues(alpha: canSend ? 1 : 0.45),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

// --- files and photos -------------------------------------------------------------------------

enum _FileChoice { photo, document }

/// What can be added, and what happens to it. The note is shown every time: the file goes to
/// the AI provider to be read.
class _AddFilesSheet extends StatelessWidget {
  const _AddFilesSheet();

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.only(bottom: OkaySpacing.lg),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: OkaySpacing.gutter),
              child: Text('Add files and photos', style: OkayText.sectionTitle),
            ),
            const Padding(
              padding: EdgeInsets.fromLTRB(
                OkaySpacing.gutter,
                OkaySpacing.xs,
                OkaySpacing.gutter,
                OkaySpacing.sm,
              ),
              child: Text(
                'O-Kay reads receipts, bills and statements. Up to 3 files, 10 MB each.',
                style: OkayText.subtitle,
              ),
            ),
            MenuRow(
              icon: Icons.photo_camera_outlined,
              title: 'Photo',
              subtitle: 'A receipt or bill, from your photos or the camera',
              onTap: () => Navigator.of(context).pop(_FileChoice.photo),
            ),
            MenuRow(
              icon: Icons.description_outlined,
              title: 'Document',
              subtitle: 'PDF, Excel (.xlsx) or CSV',
              onTap: () => Navigator.of(context).pop(_FileChoice.document),
            ),
            const Padding(
              padding: EdgeInsets.fromLTRB(
                OkaySpacing.gutter,
                OkaySpacing.md,
                OkaySpacing.gutter,
                0,
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.lock_outline_rounded, size: 16, color: OkayColors.textSecondary),
                  SizedBox(width: OkaySpacing.sm),
                  Expanded(
                    child: Text(
                      "Files are sent to O-Kay's AI service to be read and aren't kept. "
                      "Don't add ID cards, card numbers or passwords.",
                      style: OkayText.caption,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

IconData _fileIcon(AttachmentKind kind) => switch (kind) {
  AttachmentKind.photo => Icons.image_outlined,
  AttachmentKind.pdf => Icons.picture_as_pdf_outlined,
  AttachmentKind.spreadsheet => Icons.table_chart_outlined,
  AttachmentKind.file => Icons.insert_drive_file_outlined,
};

/// A small square: the photo itself, or an icon for a document.
class _FileThumb extends StatelessWidget {
  const _FileThumb(this.attachment, {this.size = 36});
  final ChatAttachment attachment;
  final double size;

  @override
  Widget build(BuildContext context) {
    final bytes = attachment.bytes;
    return ClipRRect(
      borderRadius: BorderRadius.circular(8),
      child: SizedBox.square(
        dimension: size,
        child: attachment.kind == AttachmentKind.photo && bytes != null
            ? Image.memory(
                bytes,
                fit: BoxFit.cover,
                excludeFromSemantics: true,
                errorBuilder: (context, error, stack) => _iconTile(size),
              )
            : _iconTile(size),
      ),
    );
  }
}

extension on _FileThumb {
  Widget _iconTile(double size) => ColoredBox(
    color: OkayChatColors.quickIconTile,
    child: Icon(_fileIcon(attachment.kind), size: size * 0.55, color: OkayChatColors.quickIcon),
  );
}

/// A file waiting to be sent, above the input; it can be taken off again.
class _PendingFile extends StatelessWidget {
  const _PendingFile(this.attachment, {required this.onRemove});
  final ChatAttachment attachment;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.only(left: 6),
      decoration: BoxDecoration(
        color: OkayColors.surfaceElevated,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: OkayChatColors.inputBorder),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _FileThumb(attachment),
          const SizedBox(width: OkaySpacing.sm),
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 120),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  attachment.name,
                  style: OkayText.caption.copyWith(color: OkayColors.text),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                Text(attachment.sizeLabel, style: OkayText.caption),
              ],
            ),
          ),
          IconButton(
            tooltip: 'Remove ${attachment.name}',
            onPressed: onRemove,
            icon: const Icon(Icons.close_rounded, size: 18, color: OkayColors.textSecondary),
          ),
        ],
      ),
    );
  }
}

/// A file in a sent message: the photo, or the document's icon and name.
class _SentFile extends StatelessWidget {
  const _SentFile(this.attachment);
  final ChatAttachment attachment;

  @override
  Widget build(BuildContext context) {
    final bytes = attachment.bytes;
    if (attachment.kind == AttachmentKind.photo && bytes != null) {
      return Semantics(
        label: 'Photo: ${attachment.name}',
        image: true,
        child: ClipRRect(
          borderRadius: BorderRadius.circular(12),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 220, maxHeight: 260),
            child: Image.memory(
              bytes,
              fit: BoxFit.cover,
              excludeFromSemantics: true,
              errorBuilder: (context, error, stack) => _nameRow(),
            ),
          ),
        ),
      );
    }
    return _nameRow();
  }

  Widget _nameRow() {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        _FileThumb(attachment, size: 32),
        const SizedBox(width: OkaySpacing.sm),
        Flexible(
          child: Text(
            attachment.name,
            style: OkayText.subtitle.copyWith(color: OkayColors.text),
            overflow: TextOverflow.ellipsis,
          ),
        ),
      ],
    );
  }
}
