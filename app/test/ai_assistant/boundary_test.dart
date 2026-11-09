import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// The feature must drop into the Khalti app as a folder: it may import Flutter, Dart and
/// pub packages, and its own files, but nothing else from this repo (e.g. the demo host).
void main() {
  test('lib/features/ai_assistant imports nothing from outside itself', () {
    final featureDir = Directory('lib/features/ai_assistant').absolute;
    final featureUri = featureDir.uri;
    final importRe = RegExp(r'''^\s*(?:import|export)\s+['"]([^'"]+)['"]''', multiLine: true);
    final violations = <String>[];

    for (final file in featureDir.listSync(recursive: true).whereType<File>()) {
      if (!file.path.endsWith('.dart')) continue;
      for (final m in importRe.allMatches(file.readAsStringSync())) {
        final target = m[1]!;
        if (target.startsWith('dart:')) continue;
        if (target.startsWith('package:')) {
          if (target.startsWith('package:khalti_ai_assistant/') &&
              !target.startsWith('package:khalti_ai_assistant/features/ai_assistant/')) {
            violations.add('${file.path}: $target');
          }
          continue;
        }
        final resolved = file.absolute.uri.resolve(target);
        if (!resolved.path.startsWith(featureUri.path)) {
          violations.add('${file.path}: $target');
        }
      }
    }
    expect(violations, isEmpty, reason: 'Imports leaving the feature folder');
  });
}
