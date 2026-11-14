import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/api_client.dart';
import '../core/preferences.dart';
import '../data/providers.dart';
import 'attachments.dart';
import 'chat_models.dart';
import 'chat_repository.dart';

enum ConfirmStatus { idle, saving, saved, failed, cancelled }

@immutable
class ConfirmState {
  const ConfirmState(this.status, [this.error]);
  final ConfirmStatus status;
  final String? error;
}

@immutable
class ChatState {
  const ChatState({
    this.messages = const [],
    this.sending = false,
    this.historyLoaded = false,
    this.confirmations = const {},
    this.pending = const [],
  });

  final List<ChatMessage> messages;

  /// Files added to the message being written, not sent yet.
  final List<ChatAttachment> pending;
  final bool sending;
  final bool historyLoaded;

  /// Confirm-card states, keyed by [cardKey].
  final Map<String, ConfirmState> confirmations;

  static String cardKey(int messageIndex, int cardIndex) => '$messageIndex:$cardIndex';

  /// Chips above the input: the latest answer's follow-ups, or the starter chips.
  List<Suggestion> get chips {
    for (final m in messages.reversed) {
      if (!m.isUser && !m.streaming) {
        final prompts = m.suggestions.where((s) => !s.isFeature).toList();
        if (prompts.isNotEmpty) return prompts;
        break;
      }
    }
    return starterChips;
  }

  static const starterChips = [
    Suggestion('This month vs last'),
    Suggestion('Where did my money go?'),
    Suggestion('Set a food budget'),
  ];

  ChatState copyWith({
    List<ChatMessage>? messages,
    bool? sending,
    bool? historyLoaded,
    Map<String, ConfirmState>? confirmations,
    List<ChatAttachment>? pending,
  }) => ChatState(
    messages: messages ?? this.messages,
    sending: sending ?? this.sending,
    historyLoaded: historyLoaded ?? this.historyLoaded,
    confirmations: confirmations ?? this.confirmations,
    pending: pending ?? this.pending,
  );
}

class ChatController extends Notifier<ChatState> {
  @override
  ChatState build() => const ChatState();

  ChatRepository get _repo => ref.read(chatRepositoryProvider);

  Future<void> loadHistory() async {
    if (state.historyLoaded) return;
    try {
      final history = await _repo.history();
      if (state.messages.isEmpty) state = state.copyWith(messages: history);
    } on ApiException {
      // No history is fine: the chat simply starts empty.
    }
    state = state.copyWith(historyLoaded: true);
  }

  void _updateLast(ChatMessage Function(ChatMessage) change) {
    final messages = [...state.messages];
    messages[messages.length - 1] = change(messages.last);
    state = state.copyWith(messages: messages);
  }

  /// Adds picked files to the message being written. Returns why any were left out.
  List<String> addFiles(List<PickedFile> files) {
    final problems = <String>[];
    final pending = [...state.pending];
    for (final f in files) {
      final problem = attachmentProblem(f.name, f.bytes.length);
      if (problem != null) {
        problems.add(problem);
      } else if (pending.length >= maxAttachments) {
        problems.add('Add up to $maxAttachments files at a time.');
        break;
      } else {
        pending.add(ChatAttachment(name: f.name, kind: attachmentKindFor(f.name)!, bytes: f.bytes));
      }
    }
    state = state.copyWith(pending: pending);
    return problems;
  }

  void removePending(int index) =>
      state = state.copyWith(pending: [...state.pending]..removeAt(index));

  Future<void> send(String text) async {
    final message = text.trim();
    final files = state.pending;
    if ((message.isEmpty && files.isEmpty) || state.sending) return;
    state = state.copyWith(
      sending: true,
      historyLoaded: true,
      pending: const [],
      messages: [
        ...state.messages,
        ChatMessage(role: MessageRole.user, text: message, attachments: files),
        const ChatMessage(role: MessageRole.assistant, text: '', streaming: true),
      ],
    );
    final language = ref.read(assistantPrefsProvider).language;
    try {
      await for (final ev in _repo.send(message, language: language, attachments: files)) {
        switch (ev) {
          case ToolStatusEvent(:final tool):
            _updateLast((m) => m.copyWith(toolStatus: tool));
          case ResetEvent():
            _updateLast((m) => m.copyWith(text: ''));
          case TokenEvent(:final text):
            _updateLast((m) => m.copyWith(text: m.text + text, clearToolStatus: true));
          case DoneEvent():
            _updateLast(
              (m) => m.copyWith(
                id: ev.messageId,
                cards: ev.cards.where((c) => c is! UnknownCard).toList(),
                suggestions: ev.suggestions,
                streaming: false,
                clearToolStatus: true,
                error: ev.error,
              ),
            );
        }
      }
      // Stream ended without a done event (connection dropped mid-answer).
      if (state.messages.last.streaming) {
        _updateLast(
          (m) => m.copyWith(
            streaming: false,
            clearToolStatus: true,
            text: m.text.isEmpty ? _networkText : m.text,
            error: m.text.isEmpty ? 'network' : null,
          ),
        );
      }
    } on ApiException catch (e) {
      _updateLast(
        (m) => m.copyWith(
          streaming: false,
          clearToolStatus: true,
          text: e.message,
          error: e.isRateLimited ? 'rate_limited' : (e.isNetwork ? 'network' : 'unavailable'),
        ),
      );
    } finally {
      state = state.copyWith(sending: false);
    }
  }

  static const _networkText = "Can't reach O-Kay right now. Check your connection and try again.";

  /// Re-asks the question before an answer that failed.
  Future<void> retry(int assistantIndex) async {
    if (assistantIndex < 1 || state.sending) return;
    final question = state.messages[assistantIndex - 1];
    if (!question.isUser) return;
    // Files sent in this visit are still in memory: send them again with the question.
    state = state.copyWith(
      pending: [
        for (final a in question.attachments)
          if (a.bytes != null) a,
      ],
    );
    await send(question.text);
  }

  Future<void> setFeedback(int index, String rating) async {
    final m = state.messages[index];
    if (m.id == null) return;
    final next = m.feedback == rating ? null : rating;
    _replace(index, m.copyWith(feedback: next, clearFeedback: next == null));
    try {
      await _repo.setFeedback(m.id!, next);
    } on ApiException {
      _replace(index, m); // undo
    }
  }

  void _replace(int index, ChatMessage message) {
    final messages = [...state.messages];
    messages[index] = message;
    state = state.copyWith(messages: messages);
  }

  void _setConfirm(String key, ConfirmState value) =>
      state = state.copyWith(confirmations: {...state.confirmations, key: value});

  /// The user tapped Confirm on a confirm_action card: only now is anything saved.
  Future<void> confirm(int messageIndex, int cardIndex, ConfirmActionCard card) async {
    final key = ChatState.cardKey(messageIndex, cardIndex);
    if (state.confirmations[key]?.status == ConfirmStatus.saving) return;
    _setConfirm(key, const ConfirmState(ConfirmStatus.saving));
    try {
      await _repo.confirm(card.request);
      _setConfirm(key, const ConfirmState(ConfirmStatus.saved));
      // The Budgets / Goals screens and the dashboard show the new numbers next time.
      ref.invalidate(card.action == 'upsert_goal' ? goalsProvider : budgetsProvider);
      ref
        ..invalidate(dashboardProvider)
        ..invalidate(alertsProvider); // a new budget may already be past 80%
    } on ApiException catch (e) {
      _setConfirm(key, ConfirmState(ConfirmStatus.failed, e.message));
    }
  }

  void cancelConfirm(int messageIndex, int cardIndex) => _setConfirm(
    ChatState.cardKey(messageIndex, cardIndex),
    const ConfirmState(ConfirmStatus.cancelled),
  );

  Future<void> clear() async {
    await _repo.clearHistory();
    state = const ChatState(historyLoaded: true);
  }
}

final chatControllerProvider = NotifierProvider<ChatController, ChatState>(ChatController.new);
