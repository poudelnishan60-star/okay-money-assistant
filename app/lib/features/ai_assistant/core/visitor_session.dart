/// Visitor sessions for the public website: each browser gets its own copy of the demo data.
///
/// The id comes from POST /sessions, is remembered in local storage, and is renewed when the
/// server no longer knows it (sessions expire). In the Khalti app real sign-in replaces this.
library;

import 'dart:async';
import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import '../config.dart';

abstract interface class SessionProvider {
  /// The current session id, creating one if needed.
  Future<String?> currentId();

  /// Start a fresh session (the old one expired).
  Future<String?> renew();
}

abstract interface class SessionStore {
  Future<String?> read();
  Future<void> write(String id);
  Future<void> clear();
}

class PrefsSessionStore implements SessionStore {
  static const _key = 'okay_visitor_session';

  @override
  Future<String?> read() async => (await SharedPreferences.getInstance()).getString(_key);

  @override
  Future<void> write(String id) async =>
      (await SharedPreferences.getInstance()).setString(_key, id);

  @override
  Future<void> clear() async => (await SharedPreferences.getInstance()).remove(_key);
}

class MemorySessionStore implements SessionStore {
  String? value;

  @override
  Future<String?> read() async => value;

  @override
  Future<void> write(String id) async => value = id;

  @override
  Future<void> clear() async => value = null;
}

class VisitorSession implements SessionProvider {
  VisitorSession({required this.baseUrl, required this.httpClient, required this.store});

  final Uri baseUrl;
  final http.Client httpClient;
  final SessionStore store;

  String? _id;
  Future<String?>? _creating;

  @override
  Future<String?> currentId() async {
    if (_id != null) return _id;
    _id = await store.read();
    return _id ?? renew();
  }

  @override
  Future<String?> renew() {
    // Several requests may notice the expiry at once: create only one new session.
    return _creating ??= _create().whenComplete(() => _creating = null);
  }

  Future<String?> _create() async {
    final base = baseUrl.toString().replaceFirst(RegExp(r'/+$'), '');
    final response = await httpClient
        .post(Uri.parse('$base/sessions'), headers: {'Accept': 'application/json'})
        .timeout(const Duration(seconds: 20));
    if (response.statusCode != 201) return null; // requests then go out without a session
    final body = jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, Object?>;
    final id = body['session_id']! as String;
    _id = id;
    await store.write(id);
    return id;
  }
}

final sessionStoreProvider = Provider<SessionStore>((ref) => PrefsSessionStore());

/// Null unless the host turns visitor sessions on (the public website does).
final sessionProviderProvider = Provider<SessionProvider?>((ref) {
  final config = ref.watch(assistantConfigProvider);
  if (!config.useVisitorSessions) return null;
  final client = http.Client();
  ref.onDispose(client.close);
  return VisitorSession(
    baseUrl: config.baseUrl,
    httpClient: client,
    store: ref.watch(sessionStoreProvider),
  );
});
