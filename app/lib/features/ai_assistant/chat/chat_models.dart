/// Chat models, matching the backend's /chat events and card schemas (see /openapi.json).
library;

import 'package:flutter/foundation.dart';

import '../core/api_client.dart';
import '../core/dates.dart';
import 'attachments.dart';

// --- cards ------------------------------------------------------------------------------

/// "View 12 transactions ->": GET /transactions filters for the transactions screen.
@immutable
class TransactionsLink {
  const TransactionsLink({required this.count, required this.filters});

  factory TransactionsLink.fromJson(Map<String, Object?> j) => TransactionsLink(
    count: j.integer('count'),
    filters: {
      for (final e in j.obj('filters').entries)
        if (e.value != null) e.key: e.value.toString(),
    },
  );

  final int count;
  final Map<String, String> filters;
}

sealed class ChatCard {
  const ChatCard();

  static ChatCard fromJson(Map<String, Object?> j) {
    return switch (j['type']) {
      'spending_summary' => SpendingSummaryCard.fromJson(j),
      'category_breakdown' => CategoryBreakdownCard.fromJson(j),
      'budget_progress' => BudgetProgressCard.fromJson(j),
      'bills_list' => BillsListCard.fromJson(j),
      'goal_progress' => GoalProgressCard.fromJson(j),
      'transactions_preview' => TransactionsPreviewCard.fromJson(j),
      'confirm_action' => ConfirmActionCard.fromJson(j),
      'open_app_flow' => OpenAppFlowCard.fromJson(j),
      _ => UnknownCard(j['type']?.toString() ?? '?'),
    };
  }

  /// The transactions link this card offers, if any.
  TransactionsLink? get link => null;
}

class SpendingSummaryCard extends ChatCard {
  const SpendingSummaryCard({
    required this.periodLabel,
    required this.totalPaisa,
    required this.previousPaisa,
    required this.comparedWith,
    required this.changePercent,
    required this.link,
    this.category,
  });

  factory SpendingSummaryCard.fromJson(Map<String, Object?> j) => SpendingSummaryCard(
    periodLabel: j.str('period_label'),
    category: j.strOrNull('category'),
    totalPaisa: j.integer('total_paisa'),
    previousPaisa: j.integer('previous_paisa'),
    comparedWith: j.str('compared_with'),
    changePercent: j.dblOrNull('change_percent'),
    link: TransactionsLink.fromJson(j.obj('link')),
  );

  final String periodLabel;
  final String? category;
  final int totalPaisa;
  final int previousPaisa;
  final String comparedWith;
  final double? changePercent;
  @override
  final TransactionsLink link;
}

@immutable
class CategoryAmount {
  const CategoryAmount(this.category, this.spentPaisa, this.sharePercent);
  final String category;
  final int spentPaisa;
  final double sharePercent;
}

class CategoryBreakdownCard extends ChatCard {
  const CategoryBreakdownCard({
    required this.periodLabel,
    required this.totalPaisa,
    required this.items,
    required this.link,
  });

  factory CategoryBreakdownCard.fromJson(Map<String, Object?> j) => CategoryBreakdownCard(
    periodLabel: j.str('period_label'),
    totalPaisa: j.integer('total_paisa'),
    items: [
      for (final i in j.objList('items'))
        CategoryAmount(i.str('category'), i.integer('spent_paisa'), i.dbl('share_percent')),
    ],
    link: TransactionsLink.fromJson(j.obj('link')),
  );

  final String periodLabel;
  final int totalPaisa;
  final List<CategoryAmount> items;
  @override
  final TransactionsLink link;
}

@immutable
class BudgetItem {
  const BudgetItem({
    required this.budgetId,
    required this.category,
    required this.periodLabel,
    required this.limitPaisa,
    required this.spentPaisa,
    required this.percentUsed,
    required this.level,
  });

  final int? budgetId;
  final String? category; // null = overall
  final String periodLabel;
  final int limitPaisa;
  final int spentPaisa;
  final double percentUsed;
  final String level; // ok | warning | over
}

class BudgetProgressCard extends ChatCard {
  const BudgetProgressCard(this.items);

  factory BudgetProgressCard.fromJson(Map<String, Object?> j) => BudgetProgressCard([
    for (final i in j.objList('items'))
      BudgetItem(
        budgetId: i.intOrNull('budget_id'),
        category: i.strOrNull('category'),
        periodLabel: i.str('period_label'),
        limitPaisa: i.integer('limit_paisa'),
        spentPaisa: i.integer('spent_paisa'),
        percentUsed: i.dbl('percent_used'),
        level: i.str('level'),
      ),
  ]);

  final List<BudgetItem> items;
}

@immutable
class BillItem {
  const BillItem({
    required this.billId,
    required this.merchant,
    required this.service,
    required this.usualAmountPaisa,
    required this.dueDate,
    required this.daysUntilDue,
    required this.overdue,
  });

  final String billId;
  final String merchant;
  final String? service;
  final int usualAmountPaisa;
  final DateTime dueDate;
  final int daysUntilDue;
  final bool overdue;
}

class BillsListCard extends ChatCard {
  const BillsListCard(this.items);

  factory BillsListCard.fromJson(Map<String, Object?> j) => BillsListCard([
    for (final i in j.objList('items'))
      BillItem(
        billId: i.str('bill_id'),
        merchant: i.str('merchant'),
        service: i.strOrNull('service'),
        usualAmountPaisa: i.integer('usual_amount_paisa'),
        dueDate: parseApiDate(i.str('due_date')),
        daysUntilDue: i.integer('days_until_due'),
        overdue: i.boolean('overdue'),
      ),
  ]);

  final List<BillItem> items;
}

@immutable
class GoalItem {
  const GoalItem({
    required this.goalId,
    required this.name,
    required this.targetPaisa,
    required this.savedPaisa,
    required this.percent,
    required this.deadline,
    required this.requiredMonthlyPaisa,
    required this.state,
  });

  final int goalId;
  final String name;
  final int targetPaisa;
  final int savedPaisa;
  final double percent;
  final DateTime deadline;
  final int requiredMonthlyPaisa;
  final String state; // active | done | overdue
}

class GoalProgressCard extends ChatCard {
  const GoalProgressCard(this.items);

  factory GoalProgressCard.fromJson(Map<String, Object?> j) => GoalProgressCard([
    for (final i in j.objList('items'))
      GoalItem(
        goalId: i.integer('goal_id'),
        name: i.str('name'),
        targetPaisa: i.integer('target_paisa'),
        savedPaisa: i.integer('saved_paisa'),
        percent: i.dbl('percent'),
        deadline: parseApiDate(i.str('deadline')),
        requiredMonthlyPaisa: i.integer('required_monthly_paisa'),
        state: i.str('state'),
      ),
  ]);

  final List<GoalItem> items;
}

@immutable
class TransactionItem {
  const TransactionItem(
    this.id,
    this.date,
    this.merchant,
    this.amountPaisa,
    this.isDebit,
    this.category,
  );

  final String id;
  final DateTime date;
  final String merchant;
  final int amountPaisa;
  final bool isDebit;
  final String category;
}

class TransactionsPreviewCard extends ChatCard {
  const TransactionsPreviewCard({
    required this.count,
    required this.totalDebitPaisa,
    required this.totalCreditPaisa,
    required this.items,
    required this.link,
  });

  factory TransactionsPreviewCard.fromJson(Map<String, Object?> j) => TransactionsPreviewCard(
    count: j.integer('count'),
    totalDebitPaisa: j.integer('total_debit_paisa'),
    totalCreditPaisa: j.integer('total_credit_paisa'),
    items: [
      for (final i in j.objList('items'))
        TransactionItem(
          i.str('id'),
          parseApiDate(i.str('date')),
          i.str('merchant'),
          i.integer('amount_paisa'),
          i.str('direction') == 'debit',
          i.str('category'),
        ),
    ],
    link: TransactionsLink.fromJson(j.obj('link')),
  );

  final int count;
  final int totalDebitPaisa;
  final int totalCreditPaisa;
  final List<TransactionItem> items;
  @override
  final TransactionsLink link;
}

/// The request the app makes when the user taps Confirm. Nothing was saved before that.
@immutable
class ApiRequestSpec {
  const ApiRequestSpec(this.method, this.path, this.body);
  final String method;
  final String path;
  final Map<String, Object?> body;
}

class ConfirmActionCard extends ChatCard {
  const ConfirmActionCard({
    required this.action,
    required this.title,
    required this.details,
    required this.request,
    required this.confirmLabel,
  });

  factory ConfirmActionCard.fromJson(Map<String, Object?> j) {
    final r = j.obj('request');
    return ConfirmActionCard(
      action: j.str('action'),
      title: j.str('title'),
      details: [for (final d in j.objList('details')) (d.str('label'), d.str('value'))],
      request: ApiRequestSpec(r.str('method'), r.str('path'), r.obj('body')),
      confirmLabel: j.strOrNull('confirm_label') ?? 'Confirm',
    );
  }

  final String action;
  final String title;
  final List<(String, String)> details;
  final ApiRequestSpec request;
  final String confirmLabel;
}

class OpenAppFlowCard extends ChatCard {
  const OpenAppFlowCard({
    required this.flow,
    required this.service,
    required this.title,
    required this.note,
    this.amountPaisa,
    this.billerName,
    this.recipientName,
    this.goalName,
    this.monthlyAmountPaisa,
  });

  factory OpenAppFlowCard.fromJson(Map<String, Object?> j) {
    final p = j.obj('prefill');
    return OpenAppFlowCard(
      flow: j.str('flow'),
      service: j.strOrNull('service'),
      title: j.str('title'),
      note: j.strOrNull('note') ?? '',
      amountPaisa: p.intOrNull('amount_paisa'),
      billerName: p.strOrNull('biller_name'),
      recipientName: p.strOrNull('recipient_name'),
      goalName: p.strOrNull('goal_name'),
      monthlyAmountPaisa: p.intOrNull('monthly_amount_paisa'),
    );
  }

  final String flow; // bill_payment | send_money | autopay | smart_deposit
  final String? service;
  final String title;
  final String note;
  final int? amountPaisa;
  final String? billerName;
  final String? recipientName;
  final String? goalName;
  final int? monthlyAmountPaisa;
}

/// A card type this app version doesn't know yet: skipped, never a crash.
class UnknownCard extends ChatCard {
  const UnknownCard(this.type);
  final String type;
}

// --- chips, messages, stream events ----------------------------------------------------

@immutable
class Suggestion {
  const Suggestion(this.text, {this.feature});

  factory Suggestion.fromJson(Map<String, Object?> j) => Suggestion(
    j.str('text'),
    feature: j.strOrNull('type') == 'feature' ? j.strOrNull('feature') : null,
  );

  final String text;

  /// 'smart_deposit' / 'autopay' for feature chips; null for a follow-up question.
  final String? feature;
  bool get isFeature => feature != null;
}

enum MessageRole { user, assistant }

@immutable
class ChatMessage {
  const ChatMessage({
    required this.role,
    required this.text,
    this.id,
    this.cards = const [],
    this.suggestions = const [],
    this.feedback,
    this.streaming = false,
    this.toolStatus,
    this.error,
    this.attachments = const [],
  });

  factory ChatMessage.fromJson(Map<String, Object?> j) => ChatMessage(
    id: j.integer('id'),
    role: j.str('role') == 'user' ? MessageRole.user : MessageRole.assistant,
    text: j.str('content'),
    cards: [for (final c in j.objList('cards')) ChatCard.fromJson(c)],
    suggestions: [for (final s in j.objList('suggestions')) Suggestion.fromJson(s)],
    feedback: j.strOrNull('feedback'),
    attachments: [
      for (final a in (j['attachments'] as List<Object?>? ?? const []))
        ChatAttachment.fromJson(a! as Map<String, Object?>),
    ],
  );

  final int? id;
  final MessageRole role;
  final String text;
  final List<ChatCard> cards;
  final List<Suggestion> suggestions;
  final String? feedback; // 'up' | 'down'
  final bool streaming;

  /// While a tool runs: which one (e.g. 'get_spending_summary').
  final String? toolStatus;

  /// 'busy' | 'unavailable' | 'not_configured' | 'rate_limited' | 'network'
  final String? error;

  /// Files added to a user message.
  final List<ChatAttachment> attachments;

  bool get isUser => role == MessageRole.user;

  ChatMessage copyWith({
    int? id,
    String? text,
    List<ChatCard>? cards,
    List<Suggestion>? suggestions,
    String? feedback,
    bool clearFeedback = false,
    bool? streaming,
    String? toolStatus,
    bool clearToolStatus = false,
    String? error,
  }) => ChatMessage(
    id: id ?? this.id,
    role: role,
    text: text ?? this.text,
    cards: cards ?? this.cards,
    suggestions: suggestions ?? this.suggestions,
    feedback: clearFeedback ? null : (feedback ?? this.feedback),
    streaming: streaming ?? this.streaming,
    toolStatus: clearToolStatus ? null : (toolStatus ?? this.toolStatus),
    error: error ?? this.error,
    attachments: attachments,
  );
}

sealed class ChatStreamEvent {
  const ChatStreamEvent();
}

class ToolStatusEvent extends ChatStreamEvent {
  const ToolStatusEvent(this.tool);
  final String tool;
}

/// The server took back the text streamed so far (it failed the grounding check); a
/// corrected answer follows.
class ResetEvent extends ChatStreamEvent {
  const ResetEvent();
}

class TokenEvent extends ChatStreamEvent {
  const TokenEvent(this.text);
  final String text;
}

class DoneEvent extends ChatStreamEvent {
  const DoneEvent({
    required this.messageId,
    required this.cards,
    required this.suggestions,
    required this.language,
    this.error,
  });

  factory DoneEvent.fromJson(Map<String, Object?> j) => DoneEvent(
    messageId: j.intOrNull('message_id'),
    cards: [for (final c in j.objList('cards')) ChatCard.fromJson(c)],
    suggestions: [for (final s in j.objList('suggestions')) Suggestion.fromJson(s)],
    language: j.strOrNull('language'),
    error: j.strOrNull('error'),
  );

  final int? messageId;
  final List<ChatCard> cards;
  final List<Suggestion> suggestions;
  final String? language;
  final String? error;
}
