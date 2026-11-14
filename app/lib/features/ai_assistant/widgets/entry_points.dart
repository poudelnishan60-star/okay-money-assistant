import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../routes.dart';
import '../theme/okay_theme.dart';
import 'scaffold_and_states.dart';

/// The floating "Ask me" button with the mascot slot: opens the O-Kay chat. For the host
/// app's Home (the public website has no Home: it opens straight into the chat).
class AskMeButton extends StatelessWidget {
  const AskMeButton({super.key});

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: 'Ask O-Kay',
      excludeSemantics: true,
      child: DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(OkayRadii.pill),
          boxShadow: [BoxShadow(color: OkayColors.gold.withValues(alpha: 0.25), blurRadius: 16)],
        ),
        child: Material(
          color: OkayColors.surfaceElevated,
          shape: const StadiumBorder(side: BorderSide(color: OkayColors.gold, width: 1.5)),
          child: InkWell(
            customBorder: const StadiumBorder(),
            onTap: () => context.push(OkayRoutes.chat),
            child: const Padding(
              padding: EdgeInsets.fromLTRB(6, 6, OkaySpacing.lg, 6),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  MascotSlot(size: 40, decorative: true),
                  SizedBox(width: OkaySpacing.sm),
                  Text('Ask me', style: OkayText.body),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
