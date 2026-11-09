import 'package:flutter/material.dart';

import '../widgets/widgets.dart';

/// Stand-in for screens built in later steps (5: insights, transactions, budgets, goals,
/// bills, settings; 7: chat).
class ComingSoonScreen extends StatelessWidget {
  const ComingSoonScreen({super.key, required this.title, required this.step, this.note});

  final String title;
  final int step;
  final String? note;

  @override
  Widget build(BuildContext context) {
    return OkayScaffold(
      title: title,
      showMascot: step == 7,
      body: EmptyView(
        icon: Icons.construction_outlined,
        title: '$title arrives in build step $step',
        message: note,
      ),
    );
  }
}
