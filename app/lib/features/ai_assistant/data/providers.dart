/// State for the money screens. Errors are shown with a "Try again" button, so Riverpod's
/// automatic retry is turned off ([noRetry]): retrying a 404 or a validation error is pointless.
library;

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/dates.dart';
import '../core/preferences.dart';
import 'models.dart';
import 'repositories.dart';

Duration? noRetry(int retryCount, Object error) => null;

final categoriesProvider = FutureProvider<List<CategoryInfo>>(
  (ref) => ref.watch(insightsRepositoryProvider).categories(),
  retry: noRetry,
);

/// (month 'YYYY-MM' or null for the current month, calendar 'AD' | 'BS')
typedef DashboardKey = ({String? month, String calendar});

final dashboardProvider = FutureProvider.autoDispose.family<Dashboard, DashboardKey>(
  (ref, key) =>
      ref.watch(insightsRepositoryProvider).dashboard(month: key.month, calendar: key.calendar),
  retry: noRetry,
);

// --- transactions ------------------------------------------------------------------------

@immutable
class TxnListState {
  const TxnListState({required this.page, required this.items, this.loadingMore = false});

  final TxnPage page; // totals of the whole filtered set
  final List<Txn> items; // loaded so far, newest first
  final bool loadingMore;

  bool get hasMore => items.length < page.total;
}

class TransactionsController extends AsyncNotifier<TxnListState> {
  TransactionsController(this.query);

  final TxnQuery query;
  static const pageSize = 50;

  @override
  Future<TxnListState> build() async {
    final page = await ref.watch(transactionsRepositoryProvider).page(query, limit: pageSize);
    return TxnListState(page: page, items: page.items);
  }

  Future<void> loadMore() async {
    final current = state.value;
    if (current == null || !current.hasMore || current.loadingMore) return;
    state = AsyncData(TxnListState(page: current.page, items: current.items, loadingMore: true));
    final next = await ref
        .read(transactionsRepositoryProvider)
        .page(query, offset: current.items.length, limit: pageSize);
    state = AsyncData(TxnListState(page: next, items: [...current.items, ...next.items]));
  }
}

final transactionsProvider = AsyncNotifierProvider.autoDispose
    .family<TransactionsController, TxnListState, TxnQuery>(
      TransactionsController.new,
      retry: noRetry,
    );

// --- budgets & goals ---------------------------------------------------------------------

class BudgetsController extends AsyncNotifier<List<Budget>> {
  @override
  Future<List<Budget>> build() => ref.watch(budgetsRepositoryProvider).list();

  BudgetsRepository get _repo => ref.read(budgetsRepositoryProvider);

  Future<void> upsert({
    required String? category,
    required int limitPaisa,
    required String calendar,
  }) async {
    await _repo.upsert(category: category, limitPaisa: limitPaisa, calendar: calendar);
    state = AsyncData(await _repo.list());
  }

  Future<void> edit(int id, {int? limitPaisa, String? calendar}) async {
    await _repo.update(id, limitPaisa: limitPaisa, calendar: calendar);
    state = AsyncData(await _repo.list());
  }

  Future<void> remove(int id) async {
    await _repo.delete(id);
    state = AsyncData(await _repo.list());
  }
}

final budgetsProvider = AsyncNotifierProvider<BudgetsController, List<Budget>>(
  BudgetsController.new,
  retry: noRetry,
);

class GoalsController extends AsyncNotifier<List<Goal>> {
  @override
  Future<List<Goal>> build() => ref.watch(goalsRepositoryProvider).list();

  GoalsRepository get _repo => ref.read(goalsRepositoryProvider);

  Future<void> create({
    required String name,
    required int targetPaisa,
    required int savedPaisa,
    required DateTime deadline,
  }) async {
    await _repo.create(
      name: name,
      targetPaisa: targetPaisa,
      savedPaisa: savedPaisa,
      deadline: apiDate(deadline),
    );
    state = AsyncData(await _repo.list());
  }

  Future<void> edit(
    int id, {
    String? name,
    int? targetPaisa,
    int? savedPaisa,
    DateTime? deadline,
  }) async {
    await _repo.update(
      id,
      name: name,
      targetPaisa: targetPaisa,
      savedPaisa: savedPaisa,
      deadline: deadline == null ? null : apiDate(deadline),
    );
    state = AsyncData(await _repo.list());
  }

  Future<void> remove(int id) async {
    await _repo.delete(id);
    state = AsyncData(await _repo.list());
  }
}

final goalsProvider = AsyncNotifierProvider<GoalsController, List<Goal>>(
  GoalsController.new,
  retry: noRetry,
);

final smartDepositsProvider = FutureProvider<List<SmartDeposit>>(
  (ref) => ref.watch(goalsRepositoryProvider).smartDeposits(),
  retry: noRetry,
);

// --- bills -------------------------------------------------------------------------------

class BillsController extends AsyncNotifier<List<Bill>> {
  @override
  Future<List<Bill>> build() => ref.watch(billsRepositoryProvider).list();

  /// Confirm / dismiss / undo. Updates the one row in place.
  Future<void> setStatus(String id, String status) async {
    final updated = await ref.read(billsRepositoryProvider).setStatus(id, status);
    final bills = state.value ?? const <Bill>[];
    state = AsyncData([for (final b in bills) b.id == id ? updated : b]);
  }
}

final billsProvider = AsyncNotifierProvider<BillsController, List<Bill>>(
  BillsController.new,
  retry: noRetry,
);

// --- settings ----------------------------------------------------------------------------

class SettingsController extends AsyncNotifier<AssistantSettings> {
  @override
  Future<AssistantSettings> build() async {
    final s = await ref.watch(settingsRepositoryProvider).load();
    _syncPrefs(s);
    return s;
  }

  /// Saves on the server; the screen updates at once and rolls back if saving fails.
  Future<void> save(AssistantSettings next) async {
    final previous = state.value;
    state = AsyncData(next);
    _syncPrefs(next);
    try {
      state = AsyncData(await ref.read(settingsRepositoryProvider).save(next));
    } catch (_) {
      if (previous != null) {
        state = AsyncData(previous);
        _syncPrefs(previous);
      }
      rethrow;
    }
  }

  /// The chat and cards read language/calendar from [assistantPrefsProvider].
  void _syncPrefs(AssistantSettings s) {
    final prefs = ref.read(assistantPrefsProvider.notifier);
    prefs.setLanguage(s.language);
    prefs.setCalendar(s.calendar == 'BS' ? CalendarSystem.bs : CalendarSystem.ad);
  }
}

final settingsProvider = AsyncNotifierProvider<SettingsController, AssistantSettings>(
  SettingsController.new,
  retry: noRetry,
);
