import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:khalti_ai_assistant/demo_host/demo_host_app.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/ai_assistant.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/chat/attachments.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/chat/chat_models.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/chat/chat_repository.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/core/clock.dart';

import 'fake_api.dart';

export 'fake_api.dart';

/// The fixtures' 'today': 9 Nov 2026, noon in Nepal (data runs to 8 Nov).
final fixtureNow = DateTime.utc(2026, 11, 9, 6, 15);

const demoMe = Me(
  id: 'demo_user',
  name: 'Anjali Thapa',
  balancePaisa: 2394486,
  balanceHidden: false,
);

/// Real card JSON produced by the backend tools (backend writes this fixture).
List<Map<String, Object?>> fixtureCards() => (jsonDecode(
  File('test/ai_assistant/fixtures/chat_cards.json').readAsStringSync(),
) as List<Object?>).cast<Map<String, Object?>>();

Map<String, Object?> fixtureCard(String type) =>
    fixtureCards().firstWhere((c) => c['type'] == type);

/// Phone-sized test surface (390 x 844 logical pixels).
/// Every font the app bundles (DM Sans, Noto Sans Devanagari, Material icons), from the same
/// manifest the app uses. Without this, tests draw text as wide boxes.
Future<void> loadAppFonts() async {
  final manifest = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List<Object?>;
  for (final entry in manifest.cast<Map<String, Object?>>()) {
    final loader = FontLoader(entry['family']! as String);
    for (final font in (entry['fonts']! as List<Object?>).cast<Map<String, Object?>>()) {
      loader.addFont(rootBundle.load(font['asset']! as String));
    }
    await loader.load();
  }
}

/// The app's router, from whichever screen is showing.
GoRouter routerOf(WidgetTester t) => GoRouter.of(t.element(find.byType(Navigator).first));

/// Opens the menu behind the mascot in the chat's header and, optionally, taps one item.
Future<void> openChatMenu(WidgetTester t, [String? item]) async {
  await t.tap(find.byWidgetPredicate((w) => w is PopupMenuButton));
  await t.pumpAndSettle();
  if (item != null) {
    await t.tap(find.text(item));
    await t.pumpAndSettle();
  }
}

/// Loads the mascot images for real (widget tests do not decode images on their own), so
/// golden images show them.
Future<void> loadMascot(WidgetTester t) async {
  final context = t.element(find.byType(Navigator).first);
  await t.runAsync(() async {
    for (final asset in [OkayAssets.mascot, OkayAssets.mascotAvatar]) {
      await precacheImage(AssetImage(asset), context);
    }
  });
  await t.pumpAndSettle();
}

/// Stands in for the device's file picker: returns the files queued for the next pick.
class FakeFileSource implements FileSource {
  final photos = <List<PickedFile>>[];
  final documents = <List<PickedFile>>[];

  @override
  Future<List<PickedFile>> pickPhotos() async => photos.isEmpty ? [] : photos.removeAt(0);

  @override
  Future<List<PickedFile>> pickDocuments() async => documents.isEmpty ? [] : documents.removeAt(0);
}

/// A tiny real PNG (a receipt-like sketch), so photos render in tests and golden images.
final samplePhoto = base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAADAAAABACAIAAADTQmMRAAAAYklEQVR42u3UMQ4AEBBFQcTJNM6scSuNygHUZIv5pWoim5f3XinSSgo2ICCg16v3U2v9p2DOEfqHslIDAemQDjlqIB3SIR0CAtIhHXLUQDqkQ24ICEiHdMhRAwEBAQEBPdsBXxgm5e5IM+MAAAAASUVORK5CYII=',
);

/// What the Khalti app's hide-balance eye (or Settings > Hide amounts) does.
Future<void> hideAmounts(WidgetTester t) async {
  ProviderScope.containerOf(t.element(find.byType(Navigator).first))
      .read(amountPrivacyProvider.notifier)
      .setHiddenByUser(true);
  await t.pumpAndSettle();
}

void usePhoneSize(WidgetTester tester) => useSize(tester, const Size(390, 844));

void useSize(WidgetTester tester, Size size) {
  tester.view.physicalSize = size * 3;
  tester.view.devicePixelRatio = 3;
  addTearDown(tester.view.reset);
}

/// A widget inside the assistant theme and a ProviderScope.
Widget themed(Widget child, {List<Override> overrides = const []}) => ProviderScope(
  overrides: overrides,
  child: MaterialApp(
    theme: buildOkayTheme(),
    home: Scaffold(body: child),
  ),
);

/// Scripted chat backend: each send() plays the next script.
class FakeChatRepository implements ChatRepository {
  FakeChatRepository([List<List<ChatStreamEvent>>? scripts]) : scripts = [...?scripts];

  final List<List<ChatStreamEvent>> scripts;
  final sent = <(String, String)>[];
  final confirmed = <ApiRequestSpec>[];
  final feedback = <(int, String?)>[];
  List<ChatMessage> historyMessages = [];
  Object? sendError;

  /// If set, the stream stays open after its events until this completes.
  Completer<void>? holdOpen;
  Object? confirmError;
  bool cleared = false;

  /// Names of the files sent with each message (same order as [sent]).
  final sentFiles = <List<String>>[];

  @override
  Stream<ChatStreamEvent> send(
    String message, {
    String language = 'auto',
    List<ChatAttachment> attachments = const [],
  }) async* {
    sent.add((message, language));
    sentFiles.add([for (final a in attachments) a.name]);
    if (sendError != null) throw sendError!;
    final script = scripts.isEmpty ? <ChatStreamEvent>[] : scripts.removeAt(0);
    for (final ev in script) {
      await Future<void>.delayed(Duration.zero);
      yield ev;
    }
    if (holdOpen != null) await holdOpen!.future;
  }

  @override
  Future<List<ChatMessage>> history() async => historyMessages;

  @override
  Future<void> clearHistory() async => cleared = true;

  @override
  Future<void> setFeedback(int messageId, String? rating) async =>
      feedback.add((messageId, rating));

  @override
  Future<void> confirm(ApiRequestSpec request) async {
    if (confirmError != null) throw confirmError!;
    confirmed.add(request);
  }
}

/// A typical answer: tool status, two text tokens, then cards and chips.
List<ChatStreamEvent> answer(
  String text, {
  List<String> cardTypes = const [],
  int id = 7,
  List<Suggestion> suggestions = const [Suggestion('This month vs last')],
}) => [
  const ToolStatusEvent('get_spending_summary'),
  TokenEvent(text.substring(0, text.length ~/ 2)),
  TokenEvent(text.substring(text.length ~/ 2)),
  DoneEvent(
    messageId: id,
    cards: [for (final t in cardTypes) ChatCard.fromJson(fixtureCard(t))],
    suggestions: suggestions,
    language: 'en',
  ),
];

/// The whole website (it opens on the O-Kay chat) with no network: /me and /chat are faked, the REST API is a [FakeApi]
/// answering from real backend fixtures, and there are no visitor sessions.
({Widget app, MockHostAppBridge bridge, FakeChatRepository chat, FakeApi api}) demoApp({
  bool enabled = true,
  FakeChatRepository? chat,
  FakeApi? api,
  FakeFileSource? files,
}) {
  final key = GlobalKey<NavigatorState>();
  final bridge = MockHostAppBridge(key);
  final repo = chat ?? FakeChatRepository();
  final fake = api ?? FakeApi();
  return (
    app: ProviderScope(
      overrides: [
        hostAppBridgeProvider.overrideWithValue(bridge),
        aiAssistantEnabledProvider.overrideWithValue(enabled),
        assistantConfigProvider.overrideWithValue(
          AssistantConfig(baseUrl: Uri.parse('http://test.invalid')),
        ),
        httpClientProvider.overrideWithValue(fake.client),
        meProvider.overrideWith((ref) async => demoMe),
        chatRepositoryProvider.overrideWithValue(repo),
        clockProvider.overrideWithValue(() => fixtureNow),
        fileSourceProvider.overrideWithValue(files ?? FakeFileSource()),
      ],
      child: DemoHostApp(navigatorKey: key),
    ),
    bridge: bridge,
    chat: repo,
    api: fake,
  );
}
