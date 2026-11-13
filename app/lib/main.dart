import 'package:flutter/material.dart';

import 'demo_host/demo_host_app.dart';

/// Runs the website: the O-Kay assistant on its own, opening straight into the chat.
///   flutter run -d chrome
///   flutter run --dart-define=OKAY_API_BASE_URL=http://192.168.1.10:8000   (phone on Wi-Fi)
///   flutter run --dart-define=OKAY_AI_ENABLED=false                         (flag off)
void main() {
  runApp(buildDemoApp());
}
