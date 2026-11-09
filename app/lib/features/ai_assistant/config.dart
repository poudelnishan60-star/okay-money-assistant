import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// How the host app configures the assistant. The host overrides [assistantConfigProvider].
@immutable
class AssistantConfig {
  const AssistantConfig({required this.baseUrl, this.userId, this.useVisitorSessions = false});

  /// Backend base URL, e.g. http://10.0.2.2:8000 on the Android emulator.
  final Uri baseUrl;

  /// Prototype only: sent as X-User-Id. Real Khalti auth replaces this.
  final String? userId;

  /// Public website: give each browser its own demo copy (POST /sessions, remembered locally).
  final bool useVisitorSessions;

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
