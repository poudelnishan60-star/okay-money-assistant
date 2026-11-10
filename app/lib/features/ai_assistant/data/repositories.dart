import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/api_client.dart';
import 'models.dart';

List<Map<String, Object?>> _list(Object? json) =>
    (json! as List<Object?>).cast<Map<String, Object?>>();
Map<String, Object?> _obj(Object? json) => json! as Map<String, Object?>;

class InsightsRepository {
  const InsightsRepository(this._api);
  final ApiClient _api;

  /// [month] 'YYYY-MM' in [calendar] ('AD' | 'BS'); null = the current month.
  Future<Dashboard> dashboard({String? month, String calendar = 'AD'}) async => Dashboard.fromJson(
    _obj(await _api.getJson('/insights/dashboard', query: {'month': month, 'calendar': calendar})),
  );

  Future<List<CategoryInfo>> categories() async => [
    for (final c in _list(await _api.getJson('/categories'))) CategoryInfo.fromJson(c),
  ];
}

class TransactionsRepository {
  const TransactionsRepository(this._api);
  final ApiClient _api;

  Future<TxnPage> page(TxnQuery query, {int offset = 0, int limit = 50}) async => TxnPage.fromJson(
    _obj(
      await _api.getJson(
        '/transactions',
        query: {...query.toQuery(), 'offset': offset, 'limit': limit},
      ),
    ),
  );

  /// Returns how many transactions changed (more than one with [applyToMerchant]).
  Future<int> recategorize(
    String id,
    String category, {
    String? subcategory,
    bool applyToMerchant = false,
  }) async {
    final res = _obj(
      await _api.patchJson('/transactions/$id/category', {
        'category': category,
        'subcategory': subcategory,
        'apply_to_merchant': applyToMerchant,
      }),
    );
    return (res['updated_ids']! as List<Object?>).length;
  }
}

class BudgetsRepository {
  const BudgetsRepository(this._api);
  final ApiClient _api;

  Future<List<Budget>> list() async => [
    for (final b in _list(await _api.getJson('/budgets'))) Budget.fromJson(b),
  ];

  /// Creates the budget for this category (null = overall) or replaces its limit.
  Future<void> upsert({
    required String? category,
    required int limitPaisa,
    required String calendar,
  }) => _api.postJson('/budgets', {
    'category': category,
    'limit_paisa': limitPaisa,
    'calendar': calendar,
  });

  Future<void> update(int id, {int? limitPaisa, String? calendar}) =>
      _api.patchJson('/budgets/$id', {'limit_paisa': ?limitPaisa, 'calendar': ?calendar});

  Future<void> delete(int id) => _api.delete('/budgets/$id');
}

class GoalsRepository {
  const GoalsRepository(this._api);
  final ApiClient _api;

  Future<List<Goal>> list() async => [
    for (final g in _list(await _api.getJson('/goals'))) Goal.fromJson(g),
  ];

  Future<List<SmartDeposit>> smartDeposits() async => [
    for (final d in _list(await _api.getJson('/smart-deposits'))) SmartDeposit.fromJson(d),
  ];

  Future<void> create({
    required String name,
    required int targetPaisa,
    required int savedPaisa,
    required String deadline,
  }) => _api.postJson('/goals', {
    'name': name,
    'target_paisa': targetPaisa,
    'saved_paisa': savedPaisa,
    'deadline': deadline,
  });

  Future<void> update(
    int id, {
    String? name,
    int? targetPaisa,
    int? savedPaisa,
    String? deadline,
  }) => _api.patchJson('/goals/$id', {
    'name': ?name,
    'target_paisa': ?targetPaisa,
    'saved_paisa': ?savedPaisa,
    'deadline': ?deadline,
  });

  Future<void> delete(int id) => _api.delete('/goals/$id');
}

class BillsRepository {
  const BillsRepository(this._api);
  final ApiClient _api;

  /// Detected bills and subscriptions, including dismissed ones (the screen can undo).
  Future<List<Bill>> list() async => [
    for (final b in _list(await _api.getJson('/bills', query: {'include_dismissed': true})))
      Bill.fromJson(b),
  ];

  /// 'confirmed' | 'dismissed' | 'detected' (undo).
  Future<Bill> setStatus(String id, String status) async =>
      Bill.fromJson(_obj(await _api.putJson('/bills/$id/status', {'status': status})));
}

class SettingsRepository {
  const SettingsRepository(this._api);
  final ApiClient _api;

  Future<AssistantSettings> load() async =>
      AssistantSettings.fromJson(_obj(await _api.getJson('/me/settings')));

  Future<AssistantSettings> save(AssistantSettings s) async =>
      AssistantSettings.fromJson(_obj(await _api.putJson('/me/settings', s.toJson())));
}

final insightsRepositoryProvider = Provider(
  (ref) => InsightsRepository(ref.watch(apiClientProvider)),
);
final transactionsRepositoryProvider = Provider(
  (ref) => TransactionsRepository(ref.watch(apiClientProvider)),
);
final budgetsRepositoryProvider = Provider(
  (ref) => BudgetsRepository(ref.watch(apiClientProvider)),
);
final goalsRepositoryProvider = Provider((ref) => GoalsRepository(ref.watch(apiClientProvider)));
final billsRepositoryProvider = Provider((ref) => BillsRepository(ref.watch(apiClientProvider)));
final settingsRepositoryProvider = Provider(
  (ref) => SettingsRepository(ref.watch(apiClientProvider)),
);
