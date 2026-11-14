import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/api_client.dart';
import '../core/sse.dart';
import 'attachments.dart';
import 'chat_models.dart';

/// Talks to /chat. The only place that knows the wire format of the chat stream.
class ChatRepository {
  const ChatRepository(this._api);
  final ApiClient _api;

  /// Ask O-Kay. Emits tool-status and text events as they arrive, then one DoneEvent.
  /// [language]: 'auto' | 'en' | 'ne' | 'rom'. [attachments] go as base64 in the body.
  Stream<ChatStreamEvent> send(
    String message, {
    String language = 'auto',
    List<ChatAttachment> attachments = const [],
  }) async* {
    final response = await _api.openStream(
      '/chat',
      body: {
        'message': message,
        'language': language,
        if (attachments.isNotEmpty)
          'attachments': [
            for (final a in attachments)
              if (a.bytes != null) {'name': a.name, 'data_base64': base64Encode(a.bytes!)},
          ],
      },
    );
    await for (final ev in parseSse(response.stream)) {
      final data = jsonDecode(ev.data);
      if (data is! Map<String, Object?>) continue;
      switch (ev.event) {
        case 'status':
          yield ToolStatusEvent(data.str('tool'));
        case 'token':
          yield TokenEvent(data.str('text'));
        case 'reset':
          yield const ResetEvent();
        case 'done':
          yield DoneEvent.fromJson(data);
      }
    }
  }

  Future<List<ChatMessage>> history() async {
    final list = (await _api.getJson('/chat/history'))! as List<Object?>;
    return [for (final m in list.cast<Map<String, Object?>>()) ChatMessage.fromJson(m)];
  }

  Future<void> clearHistory() => _api.delete('/chat/history');

  Future<void> setFeedback(int messageId, String? rating) =>
      _api.putJson('/chat/messages/$messageId/feedback', {'rating': rating});

  /// What a confirm_action card asks for (e.g. POST /budgets). Only allowed paths.
  Future<void> confirm(ApiRequestSpec request) async {
    const allowed = {'/budgets', '/goals'};
    final ok = allowed.contains(request.path) || RegExp(r'^/goals/\d+$').hasMatch(request.path);
    if (!ok || !{'POST', 'PATCH'}.contains(request.method)) {
      throw const ApiException('This action is not allowed from the chat.', statusCode: 400);
    }
    await _api.send(request.method, request.path, body: request.body);
  }
}

final chatRepositoryProvider = Provider<ChatRepository>(
  (ref) => ChatRepository(ref.watch(apiClientProvider)),
);
