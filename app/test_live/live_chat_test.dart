// End-to-end against a RUNNING backend (with a Groq key): the app's own chat code, a visitor
// session, the real stream. Not part of `flutter test` (lives outside test/).
//
//   cd backend && uvicorn app.main:app --port 8000        (in another terminal)
//   cd app && flutter test test_live/live_chat_test.dart
@Timeout(Duration(minutes: 3))
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:khalti_ai_assistant/features/ai_assistant/chat/chat_models.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/chat/chat_repository.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/core/api_client.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/core/visitor_session.dart';

const base = String.fromEnvironment('OKAY_API_BASE_URL', defaultValue: 'http://127.0.0.1:8000');

void main() {
  final client = http.Client();
  final store = MemorySessionStore();
  final api = ApiClient(
    baseUrl: Uri.parse(base),
    httpClient: client,
    timeout: const Duration(seconds: 60),
    session: VisitorSession(baseUrl: Uri.parse(base), httpClient: client, store: store),
  );
  final repo = ChatRepository(api);

  Future<(String, DoneEvent, List<String>, int)> ask(String q) async {
    final answer = StringBuffer();
    final tools = <String>[];
    var tokens = 0;
    var resets = 0;
    DoneEvent? done;
    await for (final ev in repo.send(q)) {
      switch (ev) {
        case ToolStatusEvent(:final tool):
          tools.add(tool);
        case ResetEvent():
          answer.clear(); // server took the text back (grounding check) and redoes it
          resets++;
        case TokenEvent(:final text):
          tokens++;
          answer.write(text);
        case DoneEvent():
          done = ev;
      }
    }
    // ignore: avoid_print
    print(
      'Q: $q\n   tools=$tools tokens=$tokens resets=$resets error=${done?.error}\n   A: $answer\n'
      '   cards=${done?.cards.map((c) => c.runtimeType).toList()} '
      'chips=${done?.suggestions.map((s) => s.text).toList()}',
    );
    return (answer.toString(), done!, tools, tokens);
  }

  test('food question streams an answer with a spending card', () async {
    final (text, done, tools, tokens) = await ask('How much did I spend on food this month?');
    expect(store.value, startsWith('v_')); // a private visitor copy was created
    expect(done.error, isNull);
    expect(tools, contains('get_spending_summary'));
    expect(tokens, greaterThan(1)); // really streamed, not one blob
    expect(text, contains('Rs.'));
    expect(done.cards.whereType<SpendingSummaryCard>(), isNotEmpty);
  });

  test('a budget is proposed, then saved only by the confirm request', () async {
    await Future<void>.delayed(const Duration(seconds: 15)); // stay inside Groq's per-minute budget
    final before = (await api.getJson('/budgets'))! as List<Object?>;
    final (_, done, _, _) = await ask('Set a food budget of 6000');
    final card = done.cards.whereType<ConfirmActionCard>().single;
    expect((await api.getJson('/budgets'))! as List<Object?>, hasLength(before.length));
    // ignore: avoid_print
    print('confirm request: ${card.request.method} ${card.request.path} ${card.request.body}');
    await repo.confirm(card.request);
    final after = ((await api.getJson('/budgets'))! as List<Object?>).cast<Map<String, Object?>>();
    // ignore: avoid_print
    print('budgets after: ${after.map((b) => '${b['category']}=${b['limit_paisa']}').toList()}');
    expect(
      after.any((b) => b['category'] == 'Food & Dining' && b['limit_paisa'] == 600000),
      isTrue,
    );
  });

  test('history and feedback round-trip', () async {
    final history = await repo.history();
    expect(history.length, greaterThanOrEqualTo(4));
    final answer = history.lastWhere((m) => !m.isUser);
    await repo.setFeedback(answer.id!, 'up');
    expect((await repo.history()).lastWhere((m) => !m.isUser).feedback, 'up');
  });
}
