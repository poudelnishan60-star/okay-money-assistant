import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

/// A stand-in backend for widget tests. Answers from the fixtures that
/// backend/scripts/export_app_fixtures.py exports from the real API, keeps budgets, goals,
/// bill statuses and settings in memory so saves show up, and records every request.
class FakeApi {
  FakeApi() {
    budgets = (_load('budgets') as List<Object?>).cast<Map<String, Object?>>().map(Map.of).toList();
    goals = (_load('goals') as List<Object?>).cast<Map<String, Object?>>().map(Map.of).toList();
    bills = (_load('bills') as List<Object?>).cast<Map<String, Object?>>().map(Map.of).toList();
    settings = Map.of(_load('settings')! as Map<String, Object?>);
    alerts = ((_load('notifications')! as Map<String, Object?>)['items']! as List<Object?>)
        .cast<Map<String, Object?>>()
        .map(Map.of)
        .toList();
  }

  static Object? _load(String name) =>
      jsonDecode(File('test/ai_assistant/fixtures/api/$name.json').readAsStringSync());

  late List<Map<String, Object?>> budgets;
  late List<Map<String, Object?>> goals;
  late List<Map<String, Object?>> bills;
  late Map<String, Object?> settings;
  late List<Map<String, Object?>> alerts;

  /// "METHOD /path?query" for every call, and the decoded bodies of writes.
  final requests = <String>[];
  final bodies = <Map<String, Object?>>[];

  late final http.Client client = MockClient(_handle);

  http.Response _json(Object? body, [int status = 200]) => http.Response.bytes(
    utf8.encode(jsonEncode(body)),
    status,
    headers: {'content-type': 'application/json'},
  );

  Future<http.Response> _handle(http.Request r) async {
    final path = r.url.path;
    final q = r.url.queryParameters;
    requests.add('${r.method} $path${r.url.hasQuery ? '?${r.url.query}' : ''}');
    final body = r.body.isEmpty ? null : jsonDecode(r.body) as Map<String, Object?>;
    if (body != null) bodies.add(body);

    switch ((r.method, path)) {
      case ('GET', '/me'):
        return _json(_load('me'));
      case ('GET', '/categories'):
        return _json(_load('categories'));
      case ('GET', '/me/settings'):
        return _json(settings);
      case ('PUT', '/me/settings'):
        settings = body!;
        return _json(settings);
      case ('GET', '/insights/dashboard'):
        if (q['calendar'] == 'BS' && q['month'] != null) return _json(_load('dashboard_kartik_bs'));
        if (q['month'] == '2026-10') return _json(_load('dashboard_oct'));
        return _json(_load('dashboard_current'));
      case ('GET', '/transactions'):
        return _json(_transactions(q));
      case ('GET', '/budgets'):
        return _json(budgets);
      case ('POST', '/budgets'):
        return _json(_upsertBudget(body!));
      case ('GET', '/goals'):
        return _json(goals);
      case ('POST', '/goals'):
        final goal = {
          ...goals.first,
          ...body!,
          'id': goals.length + 100,
          'percent': 0.0,
          'state': 'active',
          'months_left': 10,
          'required_monthly_paisa': ((body['target_paisa']! as int) / 10).ceil(),
        };
        goals.add(goal);
        return _json(goal, 201);
      case ('GET', '/smart-deposits'):
        return _json(_load('smart_deposits'));
      case ('GET', '/bills'):
        return _json(bills);
      case ('GET', '/notifications'):
        return _json({'items': alerts, 'unread': _unread});
      case ('POST', '/notifications/read'):
        final ids = (body!['ids'] as List<Object?>?)?.cast<int>();
        var updated = 0;
        for (final n in alerts) {
          if (n['read'] != true && (ids == null || ids.contains(n['id']))) {
            n['read'] = true;
            updated++;
          }
        }
        return _json({'updated': updated, 'unread': _unread});
      case ('DELETE', '/chat/history'):
        return http.Response('', 204);
    }

    final parts = path.split('/'); // ['', 'budgets', '12']
    if (parts.length >= 3) {
      final id = parts[2];
      switch ((r.method, parts[1])) {
        case ('PATCH', 'budgets'):
          final b = budgets.firstWhere((b) => '${b['id']}' == id);
          b.addAll(body!);
          return _json(b);
        case ('DELETE', 'budgets'):
          budgets.removeWhere((b) => '${b['id']}' == id);
          return http.Response('', 204);
        case ('PATCH', 'goals'):
          final g = goals.firstWhere((g) => '${g['id']}' == id);
          g.addAll(body!);
          return _json(g);
        case ('DELETE', 'goals'):
          goals.removeWhere((g) => '${g['id']}' == id);
          return http.Response('', 204);
        case ('PUT', 'bills'):
          final b = bills.firstWhere((b) => b['id'] == id);
          b['status'] = body!['status'];
          return _json(b);
        case ('PATCH', 'transactions'):
          final all =
              (_load('transactions_all')! as Map<String, Object?>)['items']! as List<Object?>;
          final t = Map.of(all.cast<Map<String, Object?>>().firstWhere((t) => t['id'] == id));
          final same = all.cast<Map<String, Object?>>().where(
            (x) => x['merchant'] == t['merchant'],
          );
          t['category'] = body!['category'];
          t['category_source'] = 'user';
          return _json({
            'transaction': t,
            'updated_ids': body['apply_to_merchant'] == true
                ? [for (final x in same) x['id']]
                : [id],
            'applied_to_merchant': body['apply_to_merchant'],
          });
      }
    }
    return _json({'detail': 'not found'}, 404);
  }

  int get _unread => alerts.where((n) => n['read'] != true).length;

  Map<String, Object?> _transactions(Map<String, String> q) {
    if (q['period'] == '7d') return _load('transactions_7d')! as Map<String, Object?>;
    if (q['category'] == 'Food & Dining' && q['period'] == 'this_month') {
      return _load('transactions_food_month')! as Map<String, Object?>;
    }
    // Anything else: the full list, paged like the real API.
    final all = _load('transactions_all')! as Map<String, Object?>;
    final items = (all['items']! as List<Object?>);
    final offset = int.tryParse(q['offset'] ?? '') ?? 0;
    final limit = int.tryParse(q['limit'] ?? '') ?? 50;
    return {
      ...all,
      'items': items.skip(offset).take(limit).toList(),
      'limit': limit,
      'offset': offset,
      'start': q['start'],
      'end': q['end'],
    };
  }

  Map<String, Object?> _upsertBudget(Map<String, Object?> body) {
    final existing = budgets.where((b) => b['category'] == body['category']).firstOrNull;
    if (existing != null) {
      existing
        ..['limit_paisa'] = body['limit_paisa']
        ..['calendar'] = body['calendar'];
      return existing;
    }
    final created = {
      ...budgets.first,
      'id': budgets.length + 100,
      'category': body['category'],
      'calendar': body['calendar'],
      'limit_paisa': body['limit_paisa'],
      'spent_paisa': 0,
      'remaining_paisa': body['limit_paisa'],
      'percent_used': 0.0,
      'level': 'ok',
      'alerts_reached': <int>[],
    };
    budgets.add(created);
    return created;
  }
}
