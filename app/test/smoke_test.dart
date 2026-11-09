import 'package:flutter_test/flutter_test.dart';
import 'package:khalti_ai_assistant/main.dart';

void main() {
  testWidgets('demo host shell boots', (tester) async {
    await tester.pumpWidget(const DemoHostApp());
    expect(find.text('O-Kay assistant prototype'), findsOneWidget);
  });
}
