import 'dart:convert';

/// One server-sent event.
class SseEvent {
  const SseEvent(this.event, this.data);
  final String event;
  final String data;

  @override
  String toString() => 'SseEvent($event, $data)';
}

/// Parses a server-sent-events byte stream (text/event-stream). Handles events split across
/// network chunks, multi-line data, comments and a final event without a blank line.
Stream<SseEvent> parseSse(Stream<List<int>> bytes) async* {
  var event = 'message';
  final data = <String>[];
  final lines = bytes.transform(utf8.decoder).transform(const LineSplitter());
  await for (final line in lines) {
    if (line.isEmpty) {
      if (data.isNotEmpty) yield SseEvent(event, data.join('\n'));
      event = 'message';
      data.clear();
      continue;
    }
    if (line.startsWith(':')) continue; // comment / keep-alive
    final colon = line.indexOf(':');
    final field = colon < 0 ? line : line.substring(0, colon);
    var value = colon < 0 ? '' : line.substring(colon + 1);
    if (value.startsWith(' ')) value = value.substring(1);
    if (field == 'event') {
      event = value;
    } else if (field == 'data') {
      data.add(value);
    }
  }
  if (data.isNotEmpty) yield SseEvent(event, data.join('\n'));
}
