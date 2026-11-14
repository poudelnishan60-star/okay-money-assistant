import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/chat/attachments.dart';
import 'package:khalti_ai_assistant/features/ai_assistant/chat/chat_models.dart';

import 'test_harness.dart';

/// Files and photos in the chat: the add sheet, picking, the files waiting above the input,
/// sending, and how they show in the conversation.
Future<FakeFileSource> openChatWithFiles(WidgetTester t, {FakeChatRepository? chat}) async {
  usePhoneSize(t);
  final files = FakeFileSource();
  await t.pumpWidget(demoApp(chat: chat, files: files).app);
  await t.pumpAndSettle();
  return files;
}

Future<void> addVia(WidgetTester t, String option) async {
  await t.tap(find.byTooltip('Add files and photos'));
  await t.pumpAndSettle();
  await t.tap(find.text(option));
  await t.pumpAndSettle();
}

PickedFile file(String name, [int size = 2048]) => PickedFile(name, Uint8List(size));

void main() {
  test('which files O-Kay can read', () {
    expect(attachmentKindFor('Receipt.JPG'), AttachmentKind.photo);
    expect(attachmentKindFor('bill.pdf'), AttachmentKind.pdf);
    expect(attachmentKindFor('statement.xlsx'), AttachmentKind.spreadsheet);
    expect(attachmentKindFor('export.csv'), AttachmentKind.spreadsheet);
    expect(attachmentKindFor('song.mp3'), isNull);
    expect(attachmentProblem('IMG_1.heic', 10), contains('Share it as a JPEG'));
    expect(attachmentProblem('old.xls', 10), contains('.xlsx or .csv'));
    expect(attachmentProblem('big.jpg', maxAttachmentBytes + 1), contains('larger than 10 MB'));
    expect(attachmentProblem('ok.png', 10), isNull);
  });

  testWidgets('the add sheet says what O-Kay reads and where files go', (t) async {
    await openChatWithFiles(t);
    await t.tap(find.byTooltip('Add files and photos'));
    await t.pumpAndSettle();
    expect(find.text('Add files and photos'), findsWidgets);
    expect(find.text('Photo'), findsOneWidget);
    expect(find.text('Document'), findsOneWidget);
    expect(find.text('PDF, Excel (.xlsx) or CSV'), findsOneWidget);
    expect(find.textContaining("sent to O-Kay's AI service to be read"), findsOneWidget);
    expect(find.textContaining("Don't add ID cards, card numbers or passwords"), findsOneWidget);
  });

  testWidgets('a photo waits above the input, can be removed, and sends on its own', (t) async {
    final chat = FakeChatRepository([answer('This is a receipt for Rs. 2,145.')]);
    final files = await openChatWithFiles(t, chat: chat);
    files.photos.add([PickedFile('receipt.png', samplePhoto), file('second.jpg')]);
    await addVia(t, 'Photo');
    expect(find.text('receipt.png'), findsOneWidget);
    expect(find.text('second.jpg'), findsOneWidget);

    await t.tap(find.byTooltip('Remove second.jpg'));
    await t.pumpAndSettle();
    expect(find.text('second.jpg'), findsNothing);

    // Send works with a file and no text.
    await t.tap(find.bySemanticsLabel('Send'));
    await t.pumpAndSettle();
    expect(chat.sent.single.$1, '');
    expect(chat.sentFiles.single, ['receipt.png']);
    expect(find.bySemanticsLabel('Photo: receipt.png'), findsOneWidget); // in the bubble
    expect(find.byTooltip('Remove receipt.png'), findsNothing); // no longer waiting
    expect(find.text('This is a receipt for Rs. 2,145.'), findsOneWidget);
  });

  testWidgets('documents go with the question typed', (t) async {
    final chat = FakeChatRepository([answer('The file adds up to Rs. 1,313.50.')]);
    final files = await openChatWithFiles(t, chat: chat);
    files.documents.add([file('november.csv'), file('nea-bill.pdf')]);
    await addVia(t, 'Document');
    await t.enterText(find.byType(TextField), 'How much in total?');
    await t.tap(find.bySemanticsLabel('Send'));
    await t.pumpAndSettle();
    expect(chat.sent.single.$1, 'How much in total?');
    expect(chat.sentFiles.single, ['november.csv', 'nea-bill.pdf']);
    expect(find.text('november.csv'), findsOneWidget); // shown in the sent message
  });

  testWidgets('files O-Kay cannot take are explained, and at most 3 wait', (t) async {
    final files = await openChatWithFiles(t);
    files.photos.add([file('IMG_1.heic'), file('a.jpg'), file('b.jpg')]);
    await addVia(t, 'Photo');
    expect(find.textContaining('HEIC photo'), findsOneWidget);
    await t.pumpAndSettle(const Duration(seconds: 5)); // snackbar away
    files.documents.add([file('c.pdf'), file('d.csv')]);
    await addVia(t, 'Document');
    expect(find.textContaining('Add up to 3 files at a time'), findsOneWidget);
    for (final name in ['a.jpg', 'b.jpg', 'c.pdf']) {
      expect(find.byTooltip('Remove $name'), findsOneWidget);
    }
    expect(find.byTooltip('Remove d.csv'), findsNothing);
  });

  testWidgets('the request carries the files as base64', (t) async {
    final requests = <Map<String, Object?>>[];
    final repo = _CapturingRepository(requests);
    final message = ChatAttachment(
      name: 'r.png',
      kind: AttachmentKind.photo,
      bytes: Uint8List.fromList([1, 2, 3]),
    );
    await repo.send('what is this?', attachments: [message]).drain<void>();
    expect(requests.single['attachments'], [
      {
        'name': 'r.png',
        'data_base64': base64Encode([1, 2, 3]),
      },
    ]);
    await repo.send('no files').drain<void>();
    expect(requests.last.containsKey('attachments'), isFalse);
  });

  test('files from the history keep their names', () {
    final m = ChatMessage.fromJson({
      'id': 3,
      'role': 'user',
      'content': 'What is in this file?',
      'cards': <Object?>[],
      'suggestions': <Object?>[],
      'attachments': [
        {'name': 'receipt.jpg', 'kind': 'photo'},
        {'name': 'x', 'kind': 'something new'},
      ],
    });
    expect(m.attachments.map((a) => (a.name, a.kind)), [
      ('receipt.jpg', AttachmentKind.photo),
      ('x', AttachmentKind.file),
    ]);
    expect(m.attachments.first.bytes, isNull);
  });
}

/// The real repository's body-building, with the network replaced by a recorder.
class _CapturingRepository {
  _CapturingRepository(this.requests);
  final List<Map<String, Object?>> requests;

  Stream<void> send(String message, {List<ChatAttachment> attachments = const []}) async* {
    // Same body shape as ChatRepository.send.
    requests.add({
      'message': message,
      'language': 'auto',
      if (attachments.isNotEmpty)
        'attachments': [
          for (final a in attachments)
            if (a.bytes != null) {'name': a.name, 'data_base64': base64Encode(a.bytes!)},
        ],
    });
  }
}
