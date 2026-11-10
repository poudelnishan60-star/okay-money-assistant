// The money screens' repositories against a RUNNING backend (no Groq key needed): reads and
// every write the screens make, in a fresh visitor session. Not part of `flutter test`.
//
//   cd backend && uvicorn app.main:app --port 8000        (in another terminal)
//   cd app && flutter test test_live/live_screens_test.dart
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:khalti_ai_assistant/features/ai_assistant/core/api_client.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/core/visitor_session.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/data/models.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/data/repositories.dart';

const base = String.fromEnvironment('OKAY_API_BASE_URL', defaultValue: 'http://127.0.0.1:8000');

void main() {
  final client = http.Client();
  final api = ApiClient(
    baseUrl: Uri.parse(base),
    httpClient: client,
    session: VisitorSession(
      baseUrl: Uri.parse(base),
      httpClient: client,
      store: MemorySessionStore(),
    ),
  );

  test('dashboard (AD and BS months) and categories', () async {
    final insights = InsightsRepository(api);
    final now = await insights.dashboard();
    expect(now.summary.inProgress, isTrue);
    expect(now.forecast, isNotNull);
    final bs = await insights.dashboard(calendar: 'BS');
    expect(bs.summary.period.label, matches(RegExp(r'^[A-Z][a-z]+ 20\d\d$'))); // e.g. Kartik 2083
    expect((await insights.categories()).map((c) => c.name), contains('Food & Dining'));
  });

  test('transactions: chips, filters, paging, recategorize', () async {
    final repo = TransactionsRepository(api);
    final month = await repo.page(const TxnQuery(period: '30d'));
    expect(month.items, isNotEmpty);
    final next = await repo.page(const TxnQuery(period: '30d'), offset: 50);
    expect(
      next.items.map((t) => t.id).toSet().intersection(month.items.map((t) => t.id).toSet()),
      isEmpty,
    );
    final food = await repo.page(const TxnQuery(period: '30d', category: 'Food & Dining'));
    expect(food.items.every((t) => t.category == 'Food & Dining'), isTrue);
    final mart = (await repo.page(const TxnQuery(period: '30d', merchant: 'Ratna Mart'))).items;
    final changed = await repo.recategorize(mart.first.id, 'Shopping', applyToMerchant: true);
    expect(changed, greaterThanOrEqualTo(mart.length));
  });

  test('budgets: create, edit, delete', () async {
    final repo = BudgetsRepository(api);
    final before = await repo.list();
    await repo.upsert(category: 'Food & Dining', limitPaisa: 600000, calendar: 'AD');
    final food = (await repo.list()).firstWhere((b) => b.category == 'Food & Dining');
    expect(food.limitPaisa, 600000);
    await repo.update(food.id, limitPaisa: 700000, calendar: 'BS');
    final edited = (await repo.list()).firstWhere((b) => b.id == food.id);
    expect((edited.limitPaisa, edited.calendar), (700000, 'BS'));
    await repo.delete(food.id);
    expect((await repo.list()).length, before.length);
  });

  test('goals and smart deposits', () async {
    final repo = GoalsRepository(api);
    await repo.create(
      name: 'Pokhara trip',
      targetPaisa: 2500000,
      savedPaisa: 0,
      deadline: '2027-09-15',
    );
    final trip = (await repo.list()).firstWhere((g) => g.name == 'Pokhara trip');
    expect(trip.requiredMonthlyPaisa, greaterThan(0));
    await repo.update(trip.id, savedPaisa: 2500000);
    expect((await repo.list()).firstWhere((g) => g.id == trip.id).state, 'done');
    await repo.delete(trip.id);
    expect(await repo.smartDeposits(), isNotEmpty);
  });

  test('bills: dismiss and undo', () async {
    final repo = BillsRepository(api);
    final first = (await repo.list()).first;
    expect((await repo.setStatus(first.id, 'dismissed')).status, 'dismissed');
    expect((await repo.setStatus(first.id, 'detected')).status, 'detected');
  });

  test('alerts: inbox, mark one read, mark all read', () async {
    final repo = AlertsRepository(api);
    final inbox = await repo.inbox();
    expect(inbox.items, isNotEmpty); // at least the weekly summary
    expect(inbox.items.map((n) => n.kind), contains('weekly_summary'));
    expect(await repo.markRead([inbox.items.first.id]), inbox.unread - 1);
    expect(await repo.markRead(), 0);
    expect((await repo.inbox()).items.every((n) => n.read), isTrue);
  });

  test('settings round-trip', () async {
    final repo = SettingsRepository(api);
    final saved = await repo.save((await repo.load()).copyWith(language: 'ne', calendar: 'BS'));
    expect((saved.language, saved.calendar), ('ne', 'BS'));
    expect((await repo.load()).language, 'ne');
  });
}
