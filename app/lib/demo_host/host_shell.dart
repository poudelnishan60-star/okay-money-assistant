import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../features/ai_assistant/ai_assistant.dart';

/// Host bottom navigation: Home, Cards, Scan & Pay (raised red circle), Transaction, Menu.
class HostShell extends StatelessWidget {
  const HostShell({super.key, required this.shell});

  final StatefulNavigationShell shell;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: shell,
      bottomNavigationBar: HostBottomNav(
        currentBranch: shell.currentIndex,
        onBranch: (i) => shell.goBranch(i, initialLocation: i == shell.currentIndex),
        onScanPay: () => showHostOnlySnack(context, 'Scan & Pay'),
      ),
    );
  }
}

void showHostOnlySnack(BuildContext context, String feature) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(content: Text('$feature is part of the Khalti app, not this demo.')));
}

class HostBottomNav extends StatelessWidget {
  const HostBottomNav({
    super.key,
    required this.currentBranch,
    required this.onBranch,
    required this.onScanPay,
  });

  final int currentBranch;
  final ValueChanged<int> onBranch;
  final VoidCallback onScanPay;

  @override
  Widget build(BuildContext context) {
    const items = [
      (Icons.home_outlined, Icons.home, 'Home'),
      (Icons.credit_card_outlined, Icons.credit_card, 'Cards'),
      (Icons.receipt_long_outlined, Icons.receipt_long, 'Transaction'),
      (Icons.menu, Icons.menu, 'Menu'),
    ];
    Widget tab(int branch) {
      final (icon, activeIcon, label) = items[branch];
      final active = branch == currentBranch;
      final color = active ? OkayColors.accentPink : OkayColors.textSecondary;
      return Expanded(
        child: Semantics(
          selected: active,
          button: true,
          label: label,
          excludeSemantics: true,
          child: InkWell(
            onTap: () => onBranch(branch),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(active ? activeIcon : icon, color: color),
                const SizedBox(height: 2),
                Text(label, style: OkayText.caption.copyWith(color: color)),
              ],
            ),
          ),
        ),
      );
    }

    return Container(
      decoration: const BoxDecoration(
        color: OkayColors.surface,
        border: Border(top: BorderSide(color: OkayColors.divider)),
      ),
      child: SafeArea(
        top: false,
        child: SizedBox(
          height: 68,
          child: Row(
            children: [
              tab(0),
              tab(1),
              Expanded(
                child: Semantics(
                  button: true,
                  label: 'Scan and Pay',
                  excludeSemantics: true,
                  child: GestureDetector(
                    onTap: onScanPay,
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.end,
                      children: [
                        Transform.translate(
                          offset: const Offset(0, -14),
                          child: Container(
                            width: OkaySizes.scanPayButton,
                            height: OkaySizes.scanPayButton,
                            decoration: const BoxDecoration(
                              color: OkayColors.primary,
                              shape: BoxShape.circle,
                              boxShadow: [BoxShadow(color: Colors.black54, blurRadius: 8)],
                            ),
                            child: const Icon(
                              Icons.qr_code_scanner,
                              color: OkayColors.text,
                              size: 30,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              tab(2),
              tab(3),
            ],
          ),
        ),
      ),
    );
  }
}

class HostPlaceholderTab extends StatelessWidget {
  const HostPlaceholderTab({super.key, required this.title, this.linkLabel, this.linkPath});

  final String title;
  final String? linkLabel;
  final String? linkPath;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(title, style: OkayText.pageTitle)),
      body: EmptyView(
        icon: Icons.phone_android_outlined,
        title: 'The Khalti app’s $title tab',
        message: 'Not part of this prototype.',
        action: linkPath == null
            ? null
            : OutlinedButton(
                onPressed: () => context.push(linkPath!),
                child: Text(linkLabel ?? 'Open'),
              ),
      ),
    );
  }
}

class MenuTab extends ConsumerWidget {
  const MenuTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final enabled = ref.watch(aiAssistantEnabledProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Menu', style: OkayText.pageTitle)),
      body: ListView(
        children: [
          if (enabled) ...[
            MenuRow(
              icon: Icons.insights_outlined,
              title: 'Money Insights',
              subtitle: 'Spending, budgets, goals and bills',
              onTap: () => context.push(OkayRoutes.insights),
            ),
            MenuRow(
              icon: Icons.receipt_outlined,
              title: 'Bills & subscriptions',
              subtitle: 'Detected recurring payments',
              onTap: () => context.push(OkayRoutes.bills),
            ),
            MenuRow(
              icon: Icons.tune_outlined,
              title: 'Assistant settings',
              subtitle: 'Language, calendar, alerts, your data',
              onTap: () => context.push(OkayRoutes.settings),
            ),
            MenuRow(
              icon: Icons.palette_outlined,
              title: 'Assistant UI kit',
              subtitle: 'Design tokens and components (developer)',
              onTap: () => context.push(OkayRoutes.uiKit),
            ),
          ],
          MenuRow(
            icon: Icons.settings_outlined,
            title: 'Settings',
            subtitle: 'Khalti app settings (host)',
            onTap: () => showHostOnlySnack(context, 'Settings'),
          ),
        ],
      ),
    );
  }
}
