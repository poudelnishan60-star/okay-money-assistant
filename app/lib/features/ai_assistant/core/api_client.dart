import 'dart:async';
import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;

import '../config.dart';
import 'dates.dart';
import 'visitor_session.dart';

/// The one way the assistant talks to its backend. Repositories use this; nothing else does.
/// No API keys ever live in the app: every LLM call happens on the backend.
class ApiClient {
  ApiClient({
    required this.baseUrl,
    http.Client? httpClient,
    this.userId,
    this.session,
    this.timeout = const Duration(seconds: 20),
  }) : _http = httpClient ?? http.Client();

  final Uri baseUrl;

  /// Fixed user (prototype header). Ignored when [session] is set.
  final String? userId;

  /// Public website: a visitor session that is created on first use and renewed if expired.
  final SessionProvider? session;
  final Duration timeout;
  final http.Client _http;

  Future<Map<String, String>> _headers({String accept = 'application/json'}) async {
    final id = session != null ? await session!.currentId() : userId;
    return {'Accept': accept, 'Content-Type': 'application/json; charset=utf-8', 'X-User-Id': ?id};
  }

  /// Builds the URL. Null query values are dropped; DateTimes become 'YYYY-MM-DD'.
  Uri uri(String path, [Map<String, Object?>? query]) {
    final params = <String, String>{};
    query?.forEach((key, value) {
      if (value == null) return;
      params[key] = value is DateTime ? apiDate(value) : value.toString();
    });
    final base = baseUrl.toString().replaceFirst(RegExp(r'/+$'), '');
    final url = Uri.parse('$base$path');
    return params.isEmpty ? url : url.replace(queryParameters: params);
  }

  Future<Object?> getJson(String path, {Map<String, Object?>? query}) =>
      send('GET', path, query: query);

  Future<Object?> postJson(String path, Object? body) => send('POST', path, body: body);

  Future<Object?> putJson(String path, Object? body) => send('PUT', path, body: body);

  Future<Object?> patchJson(String path, Object? body) => send('PATCH', path, body: body);

  Future<void> delete(String path) => send('DELETE', path);

  /// Any JSON request (e.g. the request carried by a chat confirm card).
  Future<Object?> send(
    String method,
    String path, {
    Map<String, Object?>? query,
    Object? body,
  }) async {
    final response = await _withSessionRetry<http.Response>(
      () async {
        final request = http.Request(method, uri(path, query))..headers.addAll(await _headers());
        if (body != null) request.body = jsonEncode(body);
        return http.Response.fromStream(await _http.send(request).timeout(timeout));
      },
      statusOf: (r) => r.statusCode,
      bodyOf: (r) async => r.bodyBytes,
    );
    if (response.statusCode >= 400) {
      throw ApiException.fromResponse(response.statusCode, response.bodyBytes);
    }
    if (response.statusCode == 204 || response.bodyBytes.isEmpty) return null;
    // Decode as UTF-8 explicitly: the server may not send a charset, and http would then
    // fall back to latin1 and garble 'Café' and Devanagari.
    return jsonDecode(utf8.decode(response.bodyBytes));
  }

  /// A streamed POST (the chat's server-sent events). Errors arrive as ApiException.
  Future<http.StreamedResponse> openStream(String path, {Object? body}) async {
    final response = await _withSessionRetry<http.StreamedResponse>(
      () async {
        final request = http.Request('POST', uri(path))
          ..headers.addAll(await _headers(accept: 'text/event-stream'));
        if (body != null) request.body = jsonEncode(body);
        return _http.send(request).timeout(timeout);
      },
      statusOf: (r) => r.statusCode,
      bodyOf: (r) => r.stream.toBytes(),
    );
    if (response.statusCode >= 400) {
      throw ApiException.fromResponse(response.statusCode, await response.stream.toBytes());
    }
    return response;
  }

  /// Runs [attempt]; if the visitor session is unknown or expired (401, or 404 "unknown
  /// user"), starts a new one and tries once more.
  Future<T> _withSessionRetry<T>(
    Future<T> Function() attempt, {
    required int Function(T) statusOf,
    required Future<List<int>> Function(T) bodyOf,
  }) async {
    try {
      final first = await attempt();
      final status = statusOf(first);
      if (session == null || (status != 401 && status != 404)) return first;
      final error = ApiException.fromResponse(status, await bodyOf(first));
      if (status == 404 && error.message != 'unknown user') throw error;
      await session!.renew();
      return await attempt();
    } on TimeoutException {
      throw const ApiException.network();
    } on http.ClientException {
      throw const ApiException.network();
    }
  }

  void close() => _http.close();
}

class ApiException implements Exception {
  const ApiException(this.message, {this.statusCode, this.isNetwork = false});

  const ApiException.network()
    : message = "Can't reach O-Kay right now. Check your connection and try again.",
      statusCode = null,
      isNetwork = true;

  factory ApiException.fromResponse(int status, List<int> bodyBytes) {
    String? detail;
    try {
      final decoded = jsonDecode(utf8.decode(bodyBytes));
      if (decoded is Map<String, Object?>) {
        final d = decoded['detail'];
        if (d is String) {
          detail = d;
        } else if (d is List<Object?> && d.isNotEmpty) {
          final first = d.first;
          if (first is Map<String, Object?> && first['msg'] is String) {
            detail = first['msg']! as String;
          }
        }
      }
    } on FormatException {
      detail = null;
    }
    return ApiException(detail ?? 'Something went wrong (HTTP $status).', statusCode: status);
  }

  final String message;
  final int? statusCode;
  final bool isNetwork;

  bool get isNotFound => statusCode == 404;
  bool get isRateLimited => statusCode == 429;

  @override
  String toString() => 'ApiException($statusCode): $message';
}

final httpClientProvider = Provider<http.Client>((ref) {
  final client = http.Client();
  ref.onDispose(client.close);
  return client;
});

final apiClientProvider = Provider<ApiClient>((ref) {
  final config = ref.watch(assistantConfigProvider);
  return ApiClient(
    baseUrl: config.baseUrl,
    userId: config.userId,
    session: ref.watch(sessionProviderProvider),
    httpClient: ref.watch(httpClientProvider),
  );
});

/// Small helpers for reading JSON safely under strict casts.
extension JsonRead on Map<String, Object?> {
  String str(String key) => this[key]! as String;
  String? strOrNull(String key) => this[key] as String?;
  int integer(String key) => (this[key]! as num).toInt();
  int? intOrNull(String key) => (this[key] as num?)?.toInt();
  double dbl(String key) => (this[key]! as num).toDouble();
  double? dblOrNull(String key) => (this[key] as num?)?.toDouble();
  bool boolean(String key) => this[key]! as bool;
  Map<String, Object?> obj(String key) => this[key]! as Map<String, Object?>;
  List<Map<String, Object?>> objList(String key) =>
      (this[key]! as List<Object?>).cast<Map<String, Object?>>();
}
