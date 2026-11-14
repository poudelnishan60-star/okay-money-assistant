import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/dates.dart';
import '../core/privacy.dart';
import '../host/host_app_bridge.dart';
import '../theme/okay_theme.dart';
import '../widgets/widgets.dart';

/// Developer screen: every token and shared component in one place (also the subject of the
/// golden tests in step 8). Reached from the demo host's Menu tab.
class UiKitScreen extends ConsumerStatefulWidget {
  const UiKitScreen({super.key});

  @override
  ConsumerState<UiKitScreen> createState() => _UiKitScreenState();
}

class _UiKitScreenState extends ConsumerState<UiKitScreen> {
  PeriodChoice _period = PeriodChoice.days7;
  CalendarSystem _calendar = CalendarSystem.ad;

  static const _swatches = <String, Color>{
    'background': OkayColors.background,
    'chat bg': OkayColors.chatBackground,
    'surface': OkayColors.surface,
    'elevated': OkayColors.surfaceElevated,
    'primary': OkayColors.primary,
    'user bubble': OkayColors.userBubble,
    'pink': OkayColors.accentPink,
    'tile bg': OkayColors.iconTileBackground,
    'tile icon': OkayColors.iconTileForeground,
    'gold': OkayColors.gold,
    'chip on': OkayColors.chipSelected,
    'positive': OkayColors.positive,
    'warning': OkayColors.warning,
    'danger': OkayColors.danger,
  };

  @override
  Widget build(BuildContext context) {
    final bridge = ref.watch(hostAppBridgeProvider);
    final privacy = ref.watch(amountPrivacyProvider);
    final sampleDay = DateTime.utc(2026, 11, 8);
    return OkayScaffold(
      title: 'Assistant UI kit',
      body: ListView(
        padding: const EdgeInsets.only(bottom: OkaySpacing.xxl),
        children: [
          _pad(const SectionHeader('Typography')),
          _pad(const Text('Page title 30 bold', style: OkayText.pageTitle)),
          _pad(const Text('Row title 18 medium', style: OkayText.rowTitle)),
          _pad(const Text('Subtitle 14 grey', style: OkayText.subtitle)),
          _pad(const Text('नेपाली: यो महिना खानामा कति खर्च भयो?', style: OkayText.body)),
          _pad(const SectionHeader('Colours')),
          _pad(
            Wrap(
              spacing: OkaySpacing.sm,
              runSpacing: OkaySpacing.sm,
              children: [
                for (final e in _swatches.entries)
                  Column(
                    children: [
                      Container(
                        width: 48,
                        height: 48,
                        decoration: BoxDecoration(
                          color: e.value,
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(color: OkayColors.chipBorder),
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(e.key, style: OkayText.caption),
                    ],
                  ),
              ],
            ),
          ),
          _pad(const SectionHeader('Service tiles')),
          _pad(
            Wrap(
              spacing: OkaySpacing.sm,
              runSpacing: OkaySpacing.lg,
              children: [
                ServiceIconTile(
                  icon: Icons.insights_outlined,
                  label: 'Money Insights',
                  badge: 'New',
                  onTap: () {},
                ),
                ServiceIconTile(
                  icon: Icons.savings_outlined,
                  label: 'Smart Deposit',
                  onTap: () => bridge.openSmartDeposit(
                    prefill: const SmartDepositPrefill(
                      goalName: 'New laptop',
                      monthlyAmountPaisa: 10_200_00,
                    ),
                  ),
                ),
                ServiceIconTile(
                  icon: Icons.bolt_outlined,
                  label: 'Electricity',
                  onTap: () => bridge.openBillPayment(
                    'electricity',
                    const BillPaymentPrefill(
                      billerName: 'Nepal Electricity Authority',
                      amountPaisa: 1_140_67,
                    ),
                  ),
                ),
                ServiceIconTile(
                  icon: Icons.send_outlined,
                  label: 'Send Money',
                  onTap: () => bridge.openSendMoney(
                    const SendMoneyPrefill(recipientName: 'Bikash Gurung', amountPaisa: 500_00),
                  ),
                ),
              ],
            ),
          ),
          _pad(const SectionHeader('Menu rows')),
          MenuRow(
            icon: Icons.autorenew_outlined,
            title: 'Set up Autopay',
            subtitle: 'Opens the app’s Autopay flow',
            onTap: () => bridge.openAutopay(service: 'electricity'),
          ),
          MenuRow(
            icon: Icons.fingerprint,
            title: 'Authenticate',
            subtitle: 'Mock MPIN / biometric prompt',
            onTap: () async {
              final ok = await bridge.authenticate(reason: 'Confirm your budget');
              if (context.mounted) {
                ScaffoldMessenger.of(context)
                    .showSnackBar(SnackBar(content: Text(ok ? 'Approved' : 'Cancelled')));
              }
            },
          ),
          _pad(const SectionHeader('Chips')),
          PeriodChips(selected: _period, onChanged: (p) => setState(() => _period = p)),
          _pad(const SectionHeader('Budget bars')),
          for (final pct in [45.0, 85.0, 112.0])
            _pad(
              Padding(
                padding: const EdgeInsets.only(bottom: OkaySpacing.md),
                child: Row(
                  children: [
                    SizedBox(
                      width: 48,
                      child: Text('${pct.toStringAsFixed(0)}%', style: OkayText.subtitle),
                    ),
                    Expanded(child: BudgetProgressBar(percentUsed: pct)),
                  ],
                ),
              ),
            ),
          _pad(
            SectionHeader(
              'Transactions',
              actionLabel: _calendar == CalendarSystem.ad ? 'Show BS' : 'Show AD',
              onAction: () => setState(
                () => _calendar = _calendar == CalendarSystem.ad
                    ? CalendarSystem.bs
                    : CalendarSystem.ad,
              ),
            ),
          ),
          DateGroupHeader(date: sampleDay, closingBalancePaisa: 23_944_86, calendar: _calendar),
          TransactionRow(
            icon: Icons.qr_code_scanner_outlined,
            title: 'Scan and Pay',
            merchant: 'Sasto Mitho Khaja Ghar',
            reference: 'K7Q2M9XH4TB',
            nepalTime: DateTime.utc(2026, 11, 8, 20, 22),
            amountPaisa: 240_00,
            isDebit: true,
          ),
          TransactionRow(
            icon: Icons.public_outlined,
            title: 'Remittance Received',
            merchant: 'Sagarmatha Remit',
            reference: '9XK2M4QH7TB',
            nepalTime: DateTime.utc(2026, 11, 3, 11, 5),
            amountPaisa: 27_500_00,
            isDebit: false,
          ),
          _pad(const SectionHeader('Privacy')),
          _pad(
            OkayCard(
              child: Row(
                children: [
                  const Expanded(child: Text('Balance hidden by user', style: OkayText.body)),
                  Switch(
                    value: privacy.hiddenByUser,
                    onChanged: (v) => ref.read(amountPrivacyProvider.notifier).setHiddenByUser(v),
                  ),
                ],
              ),
            ),
          ),
          _pad(const SectionHeader('Mascot slots and buttons')),
          _pad(
            Row(
              children: [
                const MascotSlot(size: 32),
                const SizedBox(width: OkaySpacing.lg),
                const MascotSlot(size: 72),
                const Spacer(),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    FilledButton(onPressed: () {}, child: const Text('Primary')),
                    const SizedBox(height: OkaySpacing.sm),
                    OutlinedButton(onPressed: () {}, child: const Text('Secondary')),
                  ],
                ),
              ],
            ),
          ),
          // The host app's entry point to the chat (the website opens in the chat instead).
          _pad(const Align(alignment: Alignment.centerLeft, child: AskMeButton())),
          _pad(const SectionHeader('States')),
          const SizedBox(height: 120, child: EmptyView(title: 'No bills found')),
          SizedBox(
            height: 180,
            child: ErrorView(message: 'Can’t reach O-Kay.', onRetry: () {}),
          ),
        ],
      ),
    );
  }

  Widget _pad(Widget child) => Padding(
    padding: const EdgeInsets.symmetric(horizontal: OkaySpacing.gutter),
    child: child,
  );
}
