import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// How the host app configures the assistant. The host overrides [assistantConfigProvider].
@immutable
class AssistantConfig {
  const AssistantConfig({
    required this.baseUrl,
    this.userId,
    this.useVisitorSessions = false,
    this.sessionDataset,
    this.hostClock,
    this.hostInbox,
  });

  /// Backend base URL, e.g. http://10.0.2.2:8000 on the Android emulator.
  final Uri baseUrl;

  /// Prototype only: sent as X-User-Id. Real Khalti auth replaces this.
  final String? userId;

  /// Public website: give each browser its own demo copy (POST /sessions, remembered locally).
  final bool useVisitorSessions;

  /// A host app with its own demo data asks for it here, e.g. 'replica' for the wallet
  /// replica's demo account, so O-Kay talks about the money the host's screens show.
  /// Null: O-Kay's own demo person.
  final String? sessionDataset;

  /// With [sessionDataset]: the moment the host made its demo data, sent with the session
  /// request so the server makes the same data (the replica's year depends on it).
  final DateTime Function()? hostClock;

  /// A host app with its own Inbox gives O-Kay its unread messages here; they go with each
  /// chat message so O-Kay can read them out when asked. Read only: O-Kay never marks
  /// them read. Null: the app has no inbox (O-Kay's own website).
  final Future<List<HostInboxMessage>> Function()? hostInbox;

  /// Compile-time settings, so builds can point elsewhere without code changes:
  ///   flutter run --dart-define=OKAY_API_BASE_URL=http://192.168.1.10:8000
  ///   flutter run --dart-define=OKAY_VISITOR_SESSIONS=false   (everyone shares the demo user)
  factory AssistantConfig.fromEnvironment() {
    const fromEnv = String.fromEnvironment('OKAY_API_BASE_URL');
    const sessions = bool.fromEnvironment('OKAY_VISITOR_SESSIONS', defaultValue: true);
    return AssistantConfig(
      baseUrl: Uri.parse(fromEnv.isNotEmpty ? fromEnv : defaultBaseUrl()),
      useVisitorSessions: sessions,
    );
  }
}

/// An unread message in the host app's own Inbox, as O-Kay is given it.
@immutable
class HostInboxMessage {
  const HostInboxMessage({
    required this.title,
    required this.body,
    required this.at,
    this.kind = '',
    this.amountPaisa,
  });

  final String title;
  final String body;
  final DateTime at;

  /// The host's own name for the kind of message, e.g. 'moneyReceived'.
  final String kind;

  /// The amount the message is about, when it has one.
  final int? amountPaisa;

  Map<String, Object?> toJson() => {
    'title': title,
    'body': body,
    'at': at.toUtc().toIso8601String(),
    if (kind.isNotEmpty) 'kind': kind,
    if (amountPaisa != null) 'amount_paisa': amountPaisa,
  };
}

/// The Android emulator reaches the host machine at 10.0.2.2; web, desktop and the iOS
/// simulator use 127.0.0.1.
String defaultBaseUrl() {
  if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
    return 'http://10.0.2.2:8000';
  }
  return 'http://127.0.0.1:8000';
}

final assistantConfigProvider = Provider<AssistantConfig>(
  (ref) => AssistantConfig.fromEnvironment(),
);

/// Feature flag: the whole assistant (entry points and routes) sits behind it.
/// Default comes from --dart-define=OKAY_AI_ENABLED=false|true (default true for the demo);
/// a host can override [aiAssistantEnabledProvider] with its remote-config value.
const bool aiAssistantEnabledByDefault = bool.fromEnvironment(
  'OKAY_AI_ENABLED',
  defaultValue: true,
);

final aiAssistantEnabledProvider = Provider<bool>((ref) => aiAssistantEnabledByDefault);
