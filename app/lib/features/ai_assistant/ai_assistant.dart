/// O-Kay AI financial assistant: the feature's public API for the host app.
///
/// The host app:
///   1. overrides [hostAppBridgeProvider] (and usually [assistantConfigProvider]),
///   2. mounts [aiAssistantRoutes] in its GoRouter,
///   3. shows entry points only when [aiAssistantEnabledProvider] is true,
///   4. keeps [amountPrivacyProvider] in sync with its "hide balance" toggle,
///   5. uses [buildOkayTheme] (or maps [OkayColors] etc. onto its own design system).
library;

export 'chat/chat_screen.dart' show ChatScreen;
export 'config.dart';
export 'core/api_client.dart' show ApiClient, ApiException, apiClientProvider, httpClientProvider;
export 'core/money.dart' show formatNpr;
export 'core/preferences.dart';
export 'core/privacy.dart';
export 'core/visitor_session.dart' show MemorySessionStore, SessionStore, sessionStoreProvider;
export 'data/me.dart' show Me, meProvider;
export 'host/host_app_bridge.dart';
export 'host/mock_host_app_bridge.dart';
export 'routes.dart';
export 'theme/okay_theme.dart';
export 'widgets/widgets.dart';
