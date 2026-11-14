import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Files and photos added in the chat: a receipt or bill photo, a PDF, an Excel file or a CSV.
/// The backend reads them to answer (photos with the AI provider's image model) and keeps
/// only their names; the bytes live in this device's memory until the message is sent.
enum AttachmentKind { photo, pdf, spreadsheet, file }

const maxAttachments = 3;
const maxAttachmentBytes = 10 * 1024 * 1024; // the backend's MAX_ATTACHMENT_MB default

const photoExtensions = ['jpg', 'jpeg', 'png', 'webp', 'gif'];
const documentExtensions = ['pdf', 'xlsx', 'csv'];

/// What a file is, from its name; null if O-Kay can't read it.
AttachmentKind? attachmentKindFor(String name) {
  final dot = name.lastIndexOf('.');
  final ext = dot < 0 ? '' : name.substring(dot + 1).toLowerCase();
  if (photoExtensions.contains(ext)) return AttachmentKind.photo;
  if (ext == 'pdf') return AttachmentKind.pdf;
  if (ext == 'xlsx' || ext == 'csv') return AttachmentKind.spreadsheet;
  return null;
}

/// Why a file can't be added, in words for the user; null if it can.
String? attachmentProblem(String name, int bytes) {
  final dot = name.lastIndexOf('.');
  final ext = dot < 0 ? '' : name.substring(dot + 1).toLowerCase();
  if (ext == 'heic' || ext == 'heif') {
    return '$name is a HEIC photo, which O-Kay can\'t read yet. Share it as a JPEG.';
  }
  if (ext == 'xls') return '$name is an old Excel file. Save it as .xlsx or .csv.';
  if (attachmentKindFor(name) == null) {
    return 'O-Kay can\'t read $name. Add a photo, a PDF, an Excel file or a CSV.';
  }
  if (bytes == 0) return '$name is empty.';
  if (bytes > maxAttachmentBytes) return '$name is larger than 10 MB.';
  return null;
}

/// A file on a message: [bytes] while it is on this device (to send it and show a photo);
/// null for files from the chat history, of which only the name is known.
@immutable
class ChatAttachment {
  const ChatAttachment({required this.name, required this.kind, this.bytes});

  factory ChatAttachment.fromJson(Map<String, Object?> j) {
    final kind = j['kind'] as String? ?? 'file';
    return ChatAttachment(
      name: j['name'] as String? ?? 'file',
      kind: AttachmentKind.values.firstWhere(
        (k) => k.name == kind,
        orElse: () => AttachmentKind.file,
      ),
    );
  }

  final String name;
  final AttachmentKind kind;
  final Uint8List? bytes;

  String get sizeLabel {
    final n = bytes?.length ?? 0;
    if (n < 1024) return '$n B';
    if (n < 1024 * 1024) return '${(n / 1024).round()} KB';
    return '${(n / (1024 * 1024)).toStringAsFixed(1)} MB';
  }
}

/// A file just picked on this device.
@immutable
class PickedFile {
  const PickedFile(this.name, this.bytes);
  final String name;
  final Uint8List bytes;
}

/// Where files come from. The default uses the device's own picker (on a phone's browser
/// "Photos" also offers the camera); the Khalti app can supply its own, and tests a fake.
abstract interface class FileSource {
  Future<List<PickedFile>> pickPhotos();
  Future<List<PickedFile>> pickDocuments();
}

class DeviceFileSource implements FileSource {
  const DeviceFileSource();

  @override
  Future<List<PickedFile>> pickPhotos() => _pick(FileType.image, null);

  @override
  Future<List<PickedFile>> pickDocuments() => _pick(FileType.custom, documentExtensions);

  Future<List<PickedFile>> _pick(FileType type, List<String>? extensions) async {
    final files = await FilePicker.pickFiles(type: type, allowedExtensions: extensions);
    return [for (final f in files) PickedFile(f.name, await f.readAsBytes())];
  }
}

final fileSourceProvider = Provider<FileSource>((ref) => const DeviceFileSource());
