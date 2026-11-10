import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../features/ai_assistant/ai_assistant.dart';
import 'host_shell.dart';

/// Host Home: balance, quick actions, Financial Services (with the new "Money Insights" tile)
/// and the floating "Ask me" button that opens O-Kay.
class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final enabled = ref.watch(aiAssistantEnabledProvider);
    final me = ref.watch(meProvider);
    final privacy = ref.watch(amountPrivacyProvider);
    final bridge = ref.watch(hostAppBridgeProvider);

    return Scaffold(
      floatingActionButton: enabled ? const AskMeButton() : null,
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: () => ref.refresh(meProvider.future),
          child: ListView(
            padding: const EdgeInsets.fromLTRB(
              OkaySpacing.gutter,
              OkaySpacing.lg,
              OkaySpacing.gutter,
              96,
            ),
            children: [
              Row(
                children: [
                  const CircleAvatar(
                    radius: 22,
                    backgroundColor: OkayColors.surfaceElevated,
                    child: Icon(Icons.person_outline, color: OkayColors.textSecondary),
                  ),
                  const SizedBox(width: OkaySpacing.md),
                  Expanded(
                    child: Text(
                      me.whenOrNull(data: (m) => 'Hi, ${m.firstName}') ?? 'Hi there',
                      style: OkayText.rowTitle,
                    ),
                  ),
                  // The demo host has no notification centre of its own: its bell shows
                  // O-Kay's alerts. Inside Khalti they arrive as push notifications.
                  if (enabled)
                    const AlertsBell()
                  else
                    IconButton(
                      onPressed: () => showHostOnlySnack(context, 'Notifications'),
                      icon: const Icon(Icons.notifications_none_outlined),
                      tooltip: 'Notifications',
                    ),
                ],
              ),
              const SizedBox(height: OkaySpacing.lg),
              OkayCard(
                padding: const EdgeInsets.all(OkaySpacing.xl),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        const Expanded(child: Text('Khalti Balance', style: OkayText.subtitle)),
                        IconButton(
                          tooltip: privacy.hiddenByUser ? 'Show balance' : 'Hide balance',
                          onPressed: () => ref
                              .read(amountPrivacyProvider.notifier)
                              .setHiddenByUser(!privacy.hiddenByUser),
                          icon: Icon(
                            privacy.hiddenByUser
                                ? Icons.visibility_off_outlined
                                : Icons.visibility_outlined,
                            color: OkayColors.textSecondary,
                          ),
                        ),
                      ],
                    ),
                    me.when(
                      data: (m) => AmountText(m.balancePaisa, style: OkayText.bigNumber),
                      loading: () => const SizedBox(
                        height: 36,
                        child: Align(
                          alignment: Alignment.centerLeft,
                          child: SizedBox.square(
                            dimension: 20,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          ),
                        ),
                      ),
                      error: (e, _) => Text(
                        e is ApiException ? e.message : 'Could not load balance',
                        style: OkayText.subtitle,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: OkaySpacing.xl),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (final (icon, label) in const [
                    (Icons.add_card_outlined, 'Load Money'),
                    (Icons.send_outlined, 'Send Money'),
                    (Icons.account_balance_outlined, 'Bank Transfer'),
                    (Icons.receipt_long_outlined, 'Pay Bills'),
                  ])
                    Expanded(
                      child: _QuickAction(
                        icon: icon,
                        label: label,
                        onTap: () => label == 'Send Money'
                            ? bridge.openSendMoney(const SendMoneyPrefill())
                            : showHostOnlySnack(context, label),
                      ),
                    ),
                ],
              ),
              const SectionHeader('Financial Services'),
              Wrap(
                spacing: OkaySpacing.xs,
                runSpacing: OkaySpacing.lg,
                children: [
                  if (enabled)
                    ServiceIconTile(
                      icon: Icons.insights_outlined,
                      label: 'Money Insights',
                      badge: 'New',
                      onTap: () => context.push(OkayRoutes.insights),
                    ),
                  ServiceIconTile(
                    icon: Icons.savings_outlined,
                    label: 'Smart Deposit',
                    onTap: () => bridge.openSmartDeposit(),
                  ),
                  ServiceIconTile(
                    icon: Icons.public_outlined,
                    label: 'Remittance',
                    onTap: () => showHostOnlySnack(context, 'Remittance'),
                  ),
                  ServiceIconTile(
                    icon: Icons.health_and_safety_outlined,
                    label: 'Insurance',
                    onTap: () => showHostOnlySnack(context, 'Insurance'),
                  ),
                ],
              ),
              const SectionHeader('Bills & Payments'),
              Wrap(
                spacing: OkaySpacing.xs,
                runSpacing: OkaySpacing.lg,
                children: [
                  for (final (icon, label, service) in const [
                    (Icons.bolt_outlined, 'Electricity', 'electricity'),
                    (Icons.water_drop_outlined, 'Khanepani', 'khanepani'),
                    (Icons.wifi_outlined, 'Internet', 'internet'),
                    (Icons.tv_outlined, 'TV', 'tv'),
                  ])
                    ServiceIconTile(
                      icon: icon,
                      label: label,
                      onTap: () => bridge.openBillPayment(service, const BillPaymentPrefill()),
                    ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _QuickAction extends StatelessWidget {
  const _QuickAction({required this.icon, required this.label, required this.onTap});

  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: label,
      excludeSemantics: true,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(OkayRadii.iconTile),
        child: SizedBox(
          width: double.infinity,
          child: Column(
            children: [
              Container(
                width: 52,
                height: 52,
                decoration: const BoxDecoration(color: OkayColors.primary, shape: BoxShape.circle),
                child: Icon(icon, color: OkayColors.text),
              ),
              const SizedBox(height: OkaySpacing.sm),
              Text(label, style: OkayText.caption, textAlign: TextAlign.center),
            ],
          ),
        ),
      ),
    );
  }
}

/// Floating "Ask me" button with the mascot slot: opens the O-Kay chat.
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
                  MascotSlot(size: 40, glow: true),
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
