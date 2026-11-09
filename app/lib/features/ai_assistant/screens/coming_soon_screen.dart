import 'package:flutter/material.dart';

import '../widgets/widgets.dart';

/// Stand-in for screens built in step 7 (insights, transactions, budgets, goals, bills,
/// settings).
class ComingSoonScreen extends StatelessWidget {
  const ComingSoonScreen({super.key, required this.title, required this.step, this.note});

  final String title;
  final int step;
  final String? note;

  @override
  Widget build(BuildContext context) {
    return OkayScaffold(
      title: title,
      body: EmptyView(
        icon: Icons.construction_outlined,
        title: '$title arrives in build step $step',
        message: note,
      ),
    );
  }
}
