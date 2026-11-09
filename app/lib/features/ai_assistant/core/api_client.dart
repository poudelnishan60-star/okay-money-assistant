import 'dart:async';
import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;

import '../config.dart';
import 'dates.dart';

/// The one way the assistant talks to its backend. Repositories use this; nothing else does.
/// No API keys ever live in the app: every LLM call happens on the backend.
class ApiClient {
  ApiClient({
    required this.baseUrl,
    http.Client? httpClient,
    this.userId,
    this.timeout = const Duration(seconds: 20),
  }) : _http = httpClient ?? http.Client();

  final Uri baseUrl;
  final String? userId;
  final Duration timeout;
  final http.Client _http;

  Map<String, String> get _headers => {
    'Accept': 'application/json',
    'Content-Type': 'application/json; charset=utf-8',
    'X-User-Id': ?userId,
  };

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
      _send('GET', path, query: query);

  Future<Object?> postJson(String path, Object? body) => _send('POST', path, body: body);

  Future<Object?> putJson(String path, Object? body) => _send('PUT', path, body: body);

  Future<Object?> patchJson(String path, Object? body) => _send('PATCH', path, body: body);

  Future<void> delete(String path) => _send('DELETE', path);

  /// A raw streamed response (for the chat's server-sent events in step 7).
  Future<http.StreamedResponse> openStream(String path, {Object? body}) async {
    final request = http.Request('POST', uri(path))
      ..headers.addAll({..._headers, 'Accept': 'text/event-stream'});
    if (body != null) request.body = jsonEncode(body);
    try {
      final response = await _http.send(request).timeout(timeout);
      if (response.statusCode >= 400) {
        final bytes = await response.stream.toBytes();
        throw ApiException.fromResponse(response.statusCode, bytes);
      }
      return response;
    } on ApiException {
      rethrow;
    } on TimeoutException {
      throw const ApiException.network();
    } on http.ClientException {
      throw const ApiException.network();
    }
  }

  Future<Object?> _send(
    String method,
    String path, {
    Map<String, Object?>? query,
    Object? body,
  }) async {
    final request = http.Request(method, uri(path, query))..headers.addAll(_headers);
    if (body != null) request.body = jsonEncode(body);
    final http.Response response;
    try {
      response = await http.Response.fromStream(await _http.send(request).timeout(timeout));
    } on TimeoutException {
      throw const ApiException.network();
    } on http.ClientException {
      throw const ApiException.network();
    }
    if (response.statusCode >= 400) {
      throw ApiException.fromResponse(response.statusCode, response.bodyBytes);
    }
    if (response.statusCode == 204 || response.bodyBytes.isEmpty) return null;
    // Decode as UTF-8 explicitly: the server may not send a charset, and http would then
    // fall back to latin1 and garble 'Café' and Devanagari.
    return jsonDecode(utf8.decode(response.bodyBytes));
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
