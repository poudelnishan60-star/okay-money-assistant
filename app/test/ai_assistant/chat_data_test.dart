import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/chat/chat_models.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/chat/chat_repository.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/config.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/core/api_client.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/core/sse.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/core/visitor_session.dart';

import 'test_harness.dart';

final _anyUrl = Uri(scheme: 'http', host: 'x');

Stream<List<int>> chunks(List<String> parts) => Stream.fromIterable(parts.map(utf8.encode));

void main() {
  group('SSE parser', () {
    test('events split across network chunks, multi-line data, comments', () async {
      final events = await parseSse(
        chunks([
          'event: tok',
          'en\ndata: {"text": "Yo ma',
          'hina"}\n\n: keep-alive\n\nevent: done\ndata: line1\ndata: line2\n\n',
          'event: tail\ndata: no blank line at the end',
        ]),
      ).toList();
      expect(events.map((e) => (e.event, e.data)), [
        ('token', '{"text": "Yo mahina"}'),
        ('done', 'line1\nline2'),
        ('tail', 'no blank line at the end'),
      ]);
    });

    test('Devanagari split mid-character still decodes', () async {
      final bytes = utf8.encode('event: token\ndata: खाजा\n\n');
      final events = await parseSse(Stream.fromIterable([bytes.sublist(0, 20), bytes.sublist(20)]))
          .toList();
      expect(events.single.data, 'खाजा');
    });
  });

  group('cards from the backend', () {
    test('every card type the backend sends parses', () {
      final cards = fixtureCards().map(ChatCard.fromJson).toList();
      expect(cards.map((c) => c.runtimeType.toString()), [
        'SpendingSummaryCard',
        'CategoryBreakdownCard',
        'BudgetProgressCard',
        'BillsListCard',
        'GoalProgressCard',
        'TransactionsPreviewCard',
        'ConfirmActionCard',
        'OpenAppFlowCard',
        // Step 11: split a bill, support, block the wallet, load money, a transaction's status.
        'OpenAppFlowCard',
        'OpenAppFlowCard',
        'OpenAppFlowCard',
        'OpenAppFlowCard',
        'TransactionsPreviewCard',
        'OpenAppFlowCard', // the refund is overdue: the support button comes with the status
        'MoneyFlowCard',
        'FileReportCard',
      ]);
      final summary = cards[0] as SpendingSummaryCard;
      expect(summary.periodLabel, 'Oct 2026');
      expect(summary.link.filters['spending_only'], 'true');
      final confirm = cards[6] as ConfirmActionCard;
      expect((confirm.request.method, confirm.request.path), ('POST', '/budgets'));
      expect(confirm.request.body['limit_paisa'], 600000);
      final flow = cards[7] as OpenAppFlowCard;
      expect((flow.flow, flow.service, flow.amountPaisa), ('bill_payment', 'electricity', 114067));

      // The backend split Rs. 1,000 between 3 in paisa: the leftover paisa is the user's.
      final split = cards[8] as OpenAppFlowCard;
      expect(split.flow, 'request_money');
      expect((split.totalPaisa, split.splitBetween, split.yourSharePaisa), (100000, 3, 33334));
      expect(split.shares, [('Sita', 33333), ('Ram', 33333)]);
      final support = cards[9] as OpenAppFlowCard;
      expect(support.flow, 'support');
      expect(support.transactionLabel, 'Nepal Telecom · Rs. 500 · 05 Nov 2026 · failed');
      expect(support.issue, 'Topup failed');
      expect((cards[10] as OpenAppFlowCard).flow, 'block_wallet');
      expect((cards[11] as OpenAppFlowCard).flow, 'load_money');
      final status = cards[12] as TransactionsPreviewCard;
      expect(status.items.single.status, 'failed');
      final overdue = cards[13] as OpenAppFlowCard;
      expect((overdue.flow, overdue.transactionId), ('support', support.transactionId));
    });

    test('an unknown card type is skipped, not a crash', () {
      expect(ChatCard.fromJson({'type': 'hologram'}), isA<UnknownCard>());
    });
  });

  group('ChatRepository', () {
    test('streams status, tokens and the final event', () async {
      final client = MockClient.streaming((request, body) async {
        expect(request.url.path, '/chat');
        expect(request.headers['Accept'], 'text/event-stream');
        expect(jsonDecode(await body.bytesToString()), {'message': 'hi', 'language': 'rom'});
        return http.StreamedResponse(
          chunks([
            'event: status\ndata: {"tool": "get_budgets"}\n\n',
            'event: token\ndata: {"text": "Namaste"}\n\n',
            'event: reset\ndata: {}\n\n',
            'event: done\ndata: {"message_id": 3, "cards": [], "suggestions": '
                '[{"text": "Smart Deposit", "type": "feature", "feature": "smart_deposit"}], '
                '"language": "rom", "error": null}\n\n',
          ]),
          200,
        );
      });
      final repo = ChatRepository(ApiClient(baseUrl: Uri.parse('http://x'), httpClient: client));
      final events = await repo.send('hi', language: 'rom').toList();
      expect((events[0] as ToolStatusEvent).tool, 'get_budgets');
      expect((events[1] as TokenEvent).text, 'Namaste');
      expect(events[2], isA<ResetEvent>());
      final done = events[3] as DoneEvent;
      expect(done.messageId, 3);
      expect(done.suggestions.single.feature, 'smart_deposit');
    });

    test("a host's unread Inbox goes with the message", () async {
      final client = MockClient.streaming((request, body) async {
        final sent = jsonDecode(await body.bytesToString()) as Map<String, Object?>;
        expect(sent['inbox'], [
          {
            'title': 'Money received',
            'body': 'Rs 2,500.00 from Ram Thapa',
            'at': '2026-11-24T13:30:00.000Z',
            'kind': 'moneyReceived',
            'amount_paisa': 250000,
          },
        ]);
        return http.StreamedResponse(
          chunks(['event: done\ndata: {"cards": [], "suggestions": []}\n\n']),
          200,
        );
      });
      final repo = ChatRepository(
        ApiClient(baseUrl: Uri.parse('http://x'), httpClient: client),
        inbox: () async => [
          HostInboxMessage(
            title: 'Money received',
            body: 'Rs 2,500.00 from Ram Thapa',
            at: DateTime.utc(2026, 11, 24, 13, 30),
            kind: 'moneyReceived',
            amountPaisa: 250000,
          ),
        ],
      );
      await repo.send('any unread messages?').toList();
    });

    test('a 429 before streaming becomes an ApiException with the server message', () async {
      final client = MockClient(
        (_) async => http.Response('{"detail": "You\'re sending messages quickly."}', 429),
      );
      final repo = ChatRepository(ApiClient(baseUrl: Uri.parse('http://x'), httpClient: client));
      await expectLater(
        repo.send('hi').toList(),
        throwsA(isA<ApiException>().having((e) => e.isRateLimited, 'rate limited', true)),
      );
    });

    test('confirm only reaches the budget and goal endpoints', () async {
      final calls = <String>[];
      final client = MockClient((r) async {
        calls.add('${r.method} ${r.url.path}');
        return http.Response('{}', 200);
      });
      final repo = ChatRepository(ApiClient(baseUrl: Uri.parse('http://x'), httpClient: client));
      await repo.confirm(const ApiRequestSpec('POST', '/budgets', {'limit_paisa': 1}));
      await repo.confirm(const ApiRequestSpec('PATCH', '/goals/3', {'name': 'x'}));
      await expectLater(
        repo.confirm(const ApiRequestSpec('POST', '/transactions', {})),
        throwsA(isA<ApiException>()),
      );
      await expectLater(
        repo.confirm(const ApiRequestSpec('DELETE', '/budgets', {})),
        throwsA(isA<ApiException>()),
      );
      expect(calls, ['POST /budgets', 'PATCH /goals/3']);
    });
  });

  group('visitor sessions', () {
    test('the website turns visitor sessions on by default', () {
      // A browser check once found every visitor sharing the demo user: guard the default.
      expect(AssistantConfig.fromEnvironment().useVisitorSessions, isTrue);
      expect(
        AssistantConfig(baseUrl: _anyUrl).useVisitorSessions,
        isFalse, // the feature itself defaults to off (the Khalti app has real sign-in)
      );
    });

    test('first request creates a session, stores it and sends it', () async {
      final seen = <String>[];
      final client = MockClient((r) async {
        seen.add('${r.method} ${r.url.path} ${r.headers['X-User-Id']}');
        if (r.url.path == '/sessions') return http.Response('{"session_id": "v_abc"}', 201);
        return http.Response('{"ok": true}', 200);
      });
      final store = MemorySessionStore();
      final session = VisitorSession(
        baseUrl: Uri.parse('http://x'),
        httpClient: client,
        store: store,
      );
      final api = ApiClient(baseUrl: Uri.parse('http://x'), httpClient: client, session: session);
      await api.getJson('/me');
      await api.getJson('/me');
      expect(seen, ['POST /sessions null', 'GET /me v_abc', 'GET /me v_abc']);
      expect(store.value, 'v_abc');
    });

    test("a host's own dataset and clock go with the session request", () async {
      final bodies = <String>[];
      final client = MockClient((r) async {
        bodies.add(r.body);
        return http.Response('{"session_id": "v_sita"}', 201);
      });
      final session = VisitorSession(
        baseUrl: Uri.parse('http://x'),
        httpClient: client,
        store: MemorySessionStore(),
        dataset: 'replica',
        hostClock: () => DateTime.utc(2026, 11, 23, 6, 15),
      );
      expect(await session.currentId(), 'v_sita');
      expect(jsonDecode(bodies.single), {'dataset': 'replica', 'now': '2026-11-23T06:15:00.000Z'});
    });

    test('an expired session is renewed once and the request retried', () async {
      var sessions = 0;
      final client = MockClient((r) async {
        if (r.url.path == '/sessions') {
          sessions++;
          return http.Response('{"session_id": "v_new$sessions"}', 201);
        }
        if (r.headers['X-User-Id'] == 'v_old') {
          return http.Response('{"detail": "unknown user"}', 404);
        }
        return http.Response('{"id": "${r.headers['X-User-Id']}"}', 200);
      });
      final store = MemorySessionStore()..value = 'v_old';
      final session = VisitorSession(
        baseUrl: Uri.parse('http://x'),
        httpClient: client,
        store: store,
      );
      final api = ApiClient(baseUrl: Uri.parse('http://x'), httpClient: client, session: session);
      expect(await api.getJson('/me'), {'id': 'v_new1'});
      expect(sessions, 1);
      expect(store.value, 'v_new1');
    });

    test('a real 404 (e.g. budget not found) is not mistaken for an expired session', () async {
      final client = MockClient((r) async {
        if (r.url.path == '/sessions') return http.Response('{"session_id": "v_x"}', 201);
        return http.Response('{"detail": "budget not found"}', 404);
      });
      final api = ApiClient(
        baseUrl: Uri.parse('http://x'),
        httpClient: client,
        session: VisitorSession(
          baseUrl: Uri.parse('http://x'),
          httpClient: client,
          store: MemorySessionStore()..value = 'v_x',
        ),
      );
      await expectLater(
        api.getJson('/budgets/9'),
        throwsA(isA<ApiException>().having((e) => e.message, 'm', 'budget not found')),
      );
    });

    test('concurrent expiries create only one new session', () async {
      var sessions = 0;
      final gate = Completer<void>();
      final client = MockClient((r) async {
        sessions++;
        await gate.future;
        return http.Response('{"session_id": "v_one"}', 201);
      });
      final session = VisitorSession(
        baseUrl: Uri.parse('http://x'),
        httpClient: client,
        store: MemorySessionStore(),
      );
      final a = session.renew();
      final b = session.renew();
      gate.complete();
      expect(await Future.wait([a, b]), ['v_one', 'v_one']);
      expect(sessions, 1);
    });
  });
}
