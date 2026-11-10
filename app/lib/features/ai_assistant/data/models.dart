/// Typed models for the REST API (see the backend's /openapi.json). Money is integer paisa.
library;

import 'package:flutter/foundation.dart';

import '../core/api_client.dart';
import '../core/dates.dart';

DateTime _date(Map<String, Object?> j, String key) => parseApiDate(j.str(key));
DateTime? _dateOrNull(Map<String, Object?> j, String key) =>
    j[key] == null ? null : parseApiDate(j.str(key));

@immutable
class PeriodInfo {
  const PeriodInfo({
    required this.start,
    required this.end,
    required this.label,
    required this.days,
  });

  factory PeriodInfo.fromJson(Map<String, Object?> j) => PeriodInfo(
    start: _date(j, 'start'),
    end: _date(j, 'end'),
    label: j.str('label'),
    days: j.integer('days'),
  );

  final DateTime start;
  final DateTime end;
  final String label;
  final int days;
}

@immutable
class CategoryInfo {
  const CategoryInfo(this.name, this.subcategories, this.countsAsSpending);

  factory CategoryInfo.fromJson(Map<String, Object?> j) => CategoryInfo(
    j.str('name'),
    (j['subcategories']! as List<Object?>).cast<String>(),
    j.boolean('counts_as_spending'),
  );

  final String name;
  final List<String> subcategories;
  final bool countsAsSpending;
}

// --- transactions ------------------------------------------------------------------------

@immutable
class Txn {
  const Txn({
    required this.id,
    required this.occurredAt,
    required this.type,
    required this.isDebit,
    required this.amountPaisa,
    required this.merchant,
    required this.category,
    this.service,
    this.reference,
    this.remarks,
    this.balanceAfterPaisa,
    this.subcategory,
    this.categorySource,
  });

  factory Txn.fromJson(Map<String, Object?> j) => Txn(
    id: j.str('id'),
    occurredAt: toNepalTime(DateTime.parse(j.str('occurred_at'))),
    type: j.str('type'),
    isDebit: j.str('direction') == 'debit',
    amountPaisa: j.integer('amount_paisa'),
    merchant: j.str('merchant'),
    service: j.strOrNull('service'),
    reference: j.strOrNull('reference'),
    remarks: j.strOrNull('remarks'),
    balanceAfterPaisa: j.intOrNull('balance_after_paisa'),
    category: j.str('category'),
    subcategory: j.strOrNull('subcategory'),
    categorySource: j.strOrNull('category_source'),
  );

  final String id;

  /// Nepal wall-clock time (see toNepalTime).
  final DateTime occurredAt;
  final String type;
  final bool isDebit;
  final int amountPaisa;
  final String merchant;
  final String? service;
  final String? reference;

  /// Free text typed by a person: show it, never act on it.
  final String? remarks;
  final int? balanceAfterPaisa;
  final String category;
  final String? subcategory;
  final String? categorySource;

  DateTime get day => DateTime.utc(occurredAt.year, occurredAt.month, occurredAt.day);
}

@immutable
class TxnPage {
  const TxnPage({
    required this.items,
    required this.total,
    required this.totalDebitPaisa,
    required this.totalCreditPaisa,
    required this.start,
    required this.end,
  });

  factory TxnPage.fromJson(Map<String, Object?> j) => TxnPage(
    items: [for (final t in j.objList('items')) Txn.fromJson(t)],
    total: j.integer('total'),
    totalDebitPaisa: j.integer('total_debit_paisa'),
    totalCreditPaisa: j.integer('total_credit_paisa'),
    start: _dateOrNull(j, 'start'),
    end: _dateOrNull(j, 'end'),
  );

  final List<Txn> items;
  final int total;
  final int totalDebitPaisa;
  final int totalCreditPaisa;
  final DateTime? start;
  final DateTime? end;
}

/// Filters for GET /transactions. Built from the period chips, a custom range, or a chat link.
@immutable
class TxnQuery {
  const TxnQuery({
    this.period,
    this.start,
    this.end,
    this.category,
    this.merchant,
    this.type,
    this.direction,
    this.spendingOnly = false,
    this.minPaisa,
    this.maxPaisa,
  });

  /// From the query parameters of a "View 12 transactions" link.
  factory TxnQuery.fromParams(Map<String, String> p) => TxnQuery(
    period: p['period'],
    start: p['start'] == null ? null : parseApiDate(p['start']!),
    end: p['end'] == null ? null : parseApiDate(p['end']!),
    category: p['category'],
    merchant: p['merchant'],
    type: p['type'],
    direction: p['direction'],
    spendingOnly: p['spending_only'] == 'true',
    minPaisa: int.tryParse(p['min_paisa'] ?? ''),
    maxPaisa: int.tryParse(p['max_paisa'] ?? ''),
  );

  final String? period; // 7d | 14d | 30d | this_month
  final DateTime? start;
  final DateTime? end;
  final String? category;
  final String? merchant;
  final String? type;
  final String? direction;
  final bool spendingOnly;
  final int? minPaisa;
  final int? maxPaisa;

  bool get hasExtraFilters =>
      category != null ||
      merchant != null ||
      type != null ||
      direction != null ||
      spendingOnly ||
      minPaisa != null ||
      maxPaisa != null;

  /// A period chip or custom range, keeping the other filters.
  TxnQuery withRange({String? period, DateTime? start, DateTime? end}) => TxnQuery(
    period: period,
    start: period == null ? start : null,
    end: period == null ? end : null,
    category: category,
    merchant: merchant,
    type: type,
    direction: direction,
    spendingOnly: spendingOnly,
    minPaisa: minPaisa,
    maxPaisa: maxPaisa,
  );

  /// The range only (filters cleared).
  TxnQuery get rangeOnly => TxnQuery(period: period, start: start, end: end);

  Map<String, Object?> toQuery() => {
    'period': period,
    'start': period == null ? start : null,
    'end': period == null ? end : null,
    'category': category,
    'merchant': merchant,
    'type': type,
    'direction': direction,
    'spending_only': spendingOnly ? 'true' : null,
    'min_paisa': minPaisa,
    'max_paisa': maxPaisa,
  };

  @override
  bool operator ==(Object other) =>
      other is TxnQuery &&
      other.period == period &&
      other.start == start &&
      other.end == end &&
      other.category == category &&
      other.merchant == merchant &&
      other.type == type &&
      other.direction == direction &&
      other.spendingOnly == spendingOnly &&
      other.minPaisa == minPaisa &&
      other.maxPaisa == maxPaisa;

  @override
  int get hashCode => Object.hash(
    period,
    start,
    end,
    category,
    merchant,
    type,
    direction,
    spendingOnly,
    minPaisa,
    maxPaisa,
  );
}

// --- insights ----------------------------------------------------------------------------

@immutable
class CategorySpend {
  const CategorySpend(
    this.category,
    this.spentPaisa,
    this.count,
    this.sharePercent,
    this.previousPaisa,
  );

  factory CategorySpend.fromJson(Map<String, Object?> j) => CategorySpend(
    j.str('category'),
    j.integer('spent_paisa'),
    j.integer('count'),
    j.dbl('share_percent'),
    j.integer('previous_spent_paisa'),
  );

  final String category;
  final int spentPaisa;
  final int count;
  final double sharePercent;
  final int previousPaisa;
}

@immutable
class MerchantSpend {
  const MerchantSpend(this.merchant, this.category, this.spentPaisa, this.count);

  factory MerchantSpend.fromJson(Map<String, Object?> j) => MerchantSpend(
    j.str('merchant'),
    j.str('category'),
    j.integer('spent_paisa'),
    j.integer('count'),
  );

  final String merchant;
  final String category;
  final int spentPaisa;
  final int count;
}

@immutable
class SpendingSummary {
  const SpendingSummary({
    required this.period,
    required this.previousPeriod,
    required this.inProgress,
    required this.coveredEnd,
    required this.totalPaisa,
    required this.previousComparePaisa,
    required this.comparisonBasis,
    required this.changePercent,
    required this.incomePaisa,
    required this.transactionCount,
    required this.byCategory,
    required this.daily,
    required this.topMerchants,
  });

  factory SpendingSummary.fromJson(Map<String, Object?> j) => SpendingSummary(
    period: PeriodInfo.fromJson(j.obj('period')),
    previousPeriod: PeriodInfo.fromJson(j.obj('previous_period')),
    inProgress: j.boolean('in_progress'),
    coveredEnd: _date(j, 'covered_end'),
    totalPaisa: j.integer('total_spent_paisa'),
    previousComparePaisa: j.integer('previous_compare_paisa'),
    comparisonBasis: j.str('comparison_basis'),
    changePercent: j.dblOrNull('change_percent'),
    incomePaisa: j.integer('income_paisa'),
    transactionCount: j.integer('transaction_count'),
    byCategory: [for (final c in j.objList('by_category')) CategorySpend.fromJson(c)],
    daily: [
      for (final d in j.objList('daily')) (date: _date(d, 'date'), paisa: d.integer('spent_paisa')),
    ],
    topMerchants: [for (final m in j.objList('top_merchants')) MerchantSpend.fromJson(m)],
  );

  final PeriodInfo period;
  final PeriodInfo previousPeriod;
  final bool inProgress;
  final DateTime coveredEnd;
  final int totalPaisa;
  final int previousComparePaisa;
  final String comparisonBasis; // same_days | full_period
  final double? changePercent;
  final int incomePaisa;
  final int transactionCount;
  final List<CategorySpend> byCategory;
  final List<({DateTime date, int paisa})> daily;
  final List<MerchantSpend> topMerchants;
}

@immutable
class Highlight {
  const Highlight(this.kind, this.severity, this.message);

  factory Highlight.fromJson(Map<String, Object?> j) =>
      Highlight(j.str('kind'), j.str('severity'), j.str('message'));

  final String kind;
  final String severity; // info | positive | warning
  final String message;
}

@immutable
class Forecast {
  const Forecast({
    required this.horizonEnd,
    required this.currentBalancePaisa,
    required this.avgDailySpendPaisa,
    required this.projectedEndPaisa,
    required this.lowestPaisa,
    required this.lowestDate,
    required this.thresholdPaisa,
    required this.belowThreshold,
    required this.firstBelowDate,
    required this.scheduled,
    required this.points,
  });

  factory Forecast.fromJson(Map<String, Object?> j) => Forecast(
    horizonEnd: _date(j, 'horizon_end'),
    currentBalancePaisa: j.integer('current_balance_paisa'),
    avgDailySpendPaisa: j.integer('avg_daily_spend_paisa'),
    projectedEndPaisa: j.integer('projected_end_balance_paisa'),
    lowestPaisa: j.integer('lowest_balance_paisa'),
    lowestDate: _date(j, 'lowest_date'),
    thresholdPaisa: j.integer('threshold_paisa'),
    belowThreshold: j.boolean('below_threshold'),
    firstBelowDate: _dateOrNull(j, 'first_below_date'),
    scheduled: [
      for (final s in j.objList('scheduled'))
        (date: _date(s, 'date'), merchant: s.str('merchant'), paisa: s.integer('amount_paisa')),
    ],
    points: [
      for (final p in j.objList('points'))
        (date: _date(p, 'date'), paisa: p.integer('balance_paisa')),
    ],
  );

  final DateTime horizonEnd;
  final int currentBalancePaisa;
  final int avgDailySpendPaisa;
  final int projectedEndPaisa;
  final int lowestPaisa;
  final DateTime lowestDate;
  final int thresholdPaisa;
  final bool belowThreshold;
  final DateTime? firstBelowDate;
  final List<({DateTime date, String merchant, int paisa})> scheduled;
  final List<({DateTime date, int paisa})> points;
}

@immutable
class Dashboard {
  const Dashboard({required this.summary, required this.highlights, this.forecast});

  factory Dashboard.fromJson(Map<String, Object?> j) => Dashboard(
    summary: SpendingSummary.fromJson(j.obj('summary')),
    highlights: [for (final h in j.objList('highlights')) Highlight.fromJson(h)],
    forecast: j['forecast'] == null ? null : Forecast.fromJson(j.obj('forecast')),
  );

  final SpendingSummary summary;
  final List<Highlight> highlights;
  final Forecast? forecast;
}

// --- budgets, goals, bills ---------------------------------------------------------------

@immutable
class Budget {
  const Budget({
    required this.id,
    required this.category,
    required this.calendar,
    required this.period,
    required this.limitPaisa,
    required this.spentPaisa,
    required this.remainingPaisa,
    required this.percentUsed,
    required this.level,
    required this.daysLeft,
    required this.dailyAllowancePaisa,
    required this.projectedPaisa,
  });

  factory Budget.fromJson(Map<String, Object?> j) => Budget(
    id: j.integer('id'),
    category: j.strOrNull('category'),
    calendar: j.str('calendar'),
    period: PeriodInfo.fromJson(j.obj('period')),
    limitPaisa: j.integer('limit_paisa'),
    spentPaisa: j.integer('spent_paisa'),
    remainingPaisa: j.integer('remaining_paisa'),
    percentUsed: j.dbl('percent_used'),
    level: j.str('level'),
    daysLeft: j.integer('days_left'),
    dailyAllowancePaisa: j.integer('daily_allowance_paisa'),
    projectedPaisa: j.integer('projected_spend_paisa'),
  );

  final int id;
  final String? category; // null = overall
  final String calendar; // AD | BS
  final PeriodInfo period;
  final int limitPaisa;
  final int spentPaisa;
  final int remainingPaisa;
  final double percentUsed;
  final String level; // ok | warning | over
  final int daysLeft;
  final int dailyAllowancePaisa;
  final int projectedPaisa;

  String get name => category ?? 'Overall';
}

@immutable
class Goal {
  const Goal({
    required this.id,
    required this.name,
    required this.targetPaisa,
    required this.savedPaisa,
    required this.deadline,
    required this.remainingPaisa,
    required this.percent,
    required this.monthsLeft,
    required this.requiredMonthlyPaisa,
    required this.state,
  });

  factory Goal.fromJson(Map<String, Object?> j) => Goal(
    id: j.integer('id'),
    name: j.str('name'),
    targetPaisa: j.integer('target_paisa'),
    savedPaisa: j.integer('saved_paisa'),
    deadline: _date(j, 'deadline'),
    remainingPaisa: j.integer('remaining_paisa'),
    percent: j.dbl('percent'),
    monthsLeft: j.integer('months_left'),
    requiredMonthlyPaisa: j.integer('required_monthly_paisa'),
    state: j.str('state'),
  );

  final int id;
  final String name;
  final int targetPaisa;
  final int savedPaisa;
  final DateTime deadline;
  final int remainingPaisa;
  final double percent;
  final int monthsLeft;
  final int requiredMonthlyPaisa;
  final String state; // active | done | overdue
}

@immutable
class SmartDeposit {
  const SmartDeposit(this.name, this.installmentPaisa, this.nextDate, this.totalPaisa);

  factory SmartDeposit.fromJson(Map<String, Object?> j) => SmartDeposit(
    j.str('name'),
    j.integer('installment_paisa'),
    _dateOrNull(j, 'next_date'),
    j.integer('total_deposited_paisa'),
  );

  final String name;
  final int installmentPaisa;
  final DateTime? nextDate;
  final int totalPaisa;
}

@immutable
class Bill {
  const Bill({
    required this.id,
    required this.merchant,
    required this.service,
    required this.category,
    required this.subcategory,
    required this.cadence,
    required this.usualAmountPaisa,
    required this.lastPaid,
    required this.dueDate,
    required this.daysUntilDue,
    required this.overdue,
    required this.status,
  });

  factory Bill.fromJson(Map<String, Object?> j) => Bill(
    id: j.str('id'),
    merchant: j.str('merchant'),
    service: j.strOrNull('service'),
    category: j.str('category'),
    subcategory: j.strOrNull('subcategory'),
    cadence: j.str('cadence'),
    usualAmountPaisa: j.integer('usual_amount_paisa'),
    lastPaid: _date(j, 'last_paid'),
    dueDate: _date(j, 'due_date'),
    daysUntilDue: j.integer('days_until_due'),
    overdue: j.boolean('overdue'),
    status: j.str('status'),
  );

  final String id;
  final String merchant;
  final String? service;
  final String category;
  final String? subcategory;
  final String cadence;
  final int usualAmountPaisa;
  final DateTime lastPaid;
  final DateTime dueDate;
  final int daysUntilDue;
  final bool overdue;
  final String status; // detected | confirmed | dismissed
}

// --- settings ----------------------------------------------------------------------------

@immutable
class AssistantSettings {
  const AssistantSettings({
    this.language = 'auto',
    this.calendar = 'AD',
    this.budgetAlerts = true,
    this.billAlerts = true,
    this.unusualAlerts = true,
    this.weeklySummary = true,
    this.weeklySummaryDay = 'sunday',
    this.lowBalanceThresholdPaisa = 100000,
  });

  factory AssistantSettings.fromJson(Map<String, Object?> j) {
    final a = j.obj('alerts');
    return AssistantSettings(
      language: j.str('language'),
      calendar: j.str('calendar'),
      budgetAlerts: a.boolean('budget'),
      billAlerts: a.boolean('bills'),
      unusualAlerts: a.boolean('unusual'),
      weeklySummary: a.boolean('weekly_summary'),
      weeklySummaryDay: j.str('weekly_summary_day'),
      lowBalanceThresholdPaisa: j.integer('low_balance_threshold_paisa'),
    );
  }

  final String language; // auto | en | ne
  final String calendar; // AD | BS
  final bool budgetAlerts;
  final bool billAlerts;
  final bool unusualAlerts;
  final bool weeklySummary;
  final String weeklySummaryDay;
  final int lowBalanceThresholdPaisa;

  Map<String, Object?> toJson() => {
    'language': language,
    'calendar': calendar,
    'alerts': {
      'budget': budgetAlerts,
      'bills': billAlerts,
      'unusual': unusualAlerts,
      'weekly_summary': weeklySummary,
    },
    'weekly_summary_day': weeklySummaryDay,
    'low_balance_threshold_paisa': lowBalanceThresholdPaisa,
  };

  AssistantSettings copyWith({
    String? language,
    String? calendar,
    bool? budgetAlerts,
    bool? billAlerts,
    bool? unusualAlerts,
    bool? weeklySummary,
    String? weeklySummaryDay,
  }) => AssistantSettings(
    language: language ?? this.language,
    calendar: calendar ?? this.calendar,
    budgetAlerts: budgetAlerts ?? this.budgetAlerts,
    billAlerts: billAlerts ?? this.billAlerts,
    unusualAlerts: unusualAlerts ?? this.unusualAlerts,
    weeklySummary: weeklySummary ?? this.weeklySummary,
    weeklySummaryDay: weeklySummaryDay ?? this.weeklySummaryDay,
    lowBalanceThresholdPaisa: lowBalanceThresholdPaisa,
  );
}
