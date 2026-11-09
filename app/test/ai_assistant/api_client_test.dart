import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/core/api_client.dart';

ApiClient clientWith(MockClientHandler handler, {String? userId}) => ApiClient(
  baseUrl: Uri.parse('http://127.0.0.1:8000/'),
  httpClient: MockClient(handler),
  userId: userId,
);

void main() {
  test('builds URLs: drops nulls, formats dates, keeps the base path clean', () {
    final api = clientWith((_) async => http.Response('{}', 200));
    final url = api.uri('/transactions', {
      'category': 'Food & Dining',
      'start': DateTime(2026, 10, 1),
      'merchant': null,
      'limit': 50,
    });
    expect(url.toString(), startsWith('http://127.0.0.1:8000/transactions?'));
    expect(url.queryParameters, {
      'category': 'Food & Dining',
      'start': '2026-10-01',
      'limit': '50',
    });
  });

  test('sends JSON headers and the prototype user header', () async {
    late http.BaseRequest seen;
    final api = clientWith((req) async {
      seen = req;
      return http.Response('{"ok": true}', 200);
    }, userId: 'demo_user');
    final body = await api.postJson('/budgets', {'limit_paisa': 600000});
    expect(body, {'ok': true});
    expect(seen.method, 'POST');
    expect(seen.headers['X-User-Id'], 'demo_user');
    expect(seen.headers['Accept'], 'application/json');
    expect(jsonDecode((seen as http.Request).body), {'limit_paisa': 600000});
  });

  test('decodes UTF-8 even when the server sends no charset', () async {
    final bytes = utf8.encode('{"merchant": "Café Dhukuti", "ne": "खाजा"}');
    final api = clientWith(
      (_) async => http.Response.bytes(bytes, 200, headers: {'content-type': 'application/json'}),
    );
    final body = (await api.getJson('/x'))! as Map<String, Object?>;
    expect(body['merchant'], 'Café Dhukuti');
    expect(body['ne'], 'खाजा');
  });

  test('204 and empty bodies return null', () async {
    final api = clientWith((_) async => http.Response('', 204));
    await api.delete('/budgets/1');
    expect(await api.getJson('/empty'), isNull);
  });

  test('FastAPI errors become ApiException with the server message', () async {
    final notFound = clientWith((_) async => http.Response('{"detail": "budget not found"}', 404));
    await expectLater(
      notFound.getJson('/budgets/9'),
      throwsA(
        isA<ApiException>()
            .having((e) => e.statusCode, 'status', 404)
            .having((e) => e.message, 'message', 'budget not found')
            .having((e) => e.isNotFound, 'isNotFound', true),
      ),
    );

    final invalid = clientWith(
      (_) async => http.Response(
        '{"detail": [{"loc": ["body", "limit_paisa"], "msg": "Input should be greater than 0"}]}',
        422,
      ),
    );
    await expectLater(
      invalid.postJson('/budgets', {}),
      throwsA(isA<ApiException>().having((e) => e.message, 'm', 'Input should be greater than 0')),
    );

    final html = clientWith((_) async => http.Response('<h1>Bad gateway</h1>', 502));
    await expectLater(
      html.getJson('/x'),
      throwsA(isA<ApiException>().having((e) => e.message, 'm', contains('HTTP 502'))),
    );
  });

  test('network failures become a friendly ApiException', () async {
    final api = clientWith((_) async => throw http.ClientException('connection refused'));
    await expectLater(
      api.getJson('/me'),
      throwsA(isA<ApiException>().having((e) => e.isNetwork, 'isNetwork', true)),
    );
  });

  test('JSON helpers read under strict casts', () {
    final json = <String, Object?>{'a': 'x', 'n': 3, 'd': 2.5, 'b': true, 'nil': null};
    expect(json.str('a'), 'x');
    expect(json.integer('n'), 3);
    expect(json.dbl('n'), 3.0);
    expect(json.dblOrNull('nil'), isNull);
    expect(json.boolean('b'), isTrue);
  });
}
