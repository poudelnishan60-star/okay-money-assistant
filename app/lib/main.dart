import 'package:flutter/material.dart';

/// Demo host shell. In step 4 this mounts the AI assistant feature
/// (lib/features/ai_assistant/) behind a feature flag.
void main() {
  runApp(const DemoHostApp());
}

class DemoHostApp extends StatelessWidget {
  const DemoHostApp({super.key});

  @override
  Widget build(BuildContext context) {
    return const MaterialApp(
      title: 'O-Kay Assistant (prototype)',
      debugShowCheckedModeBanner: false,
      home: Scaffold(body: Center(child: Text('O-Kay assistant prototype'))),
    );
  }
}
