import 'package:flutter/material.dart';

import '../core/money.dart';
import '../theme/okay_theme.dart';
import 'host_app_bridge.dart';

/// Stand-in for the Khalti app: shows a "would open X" sheet instead of a real flow.
class MockHostAppBridge implements HostAppBridge {
  MockHostAppBridge(this.navigatorKey);

  final GlobalKey<NavigatorState> navigatorKey;

  /// Every call, newest last (handy in tests and for the UI kit screen).
  final List<String> calls = [];

  @override
  Future<void> openSendMoney(SendMoneyPrefill prefill) {
    calls.add('openSendMoney');
    return _show('Send Money', {
      'To': prefill.recipientName,
      'Amount': _amount(prefill.amountPaisa),
      'Note': prefill.note,
    });
  }

  @override
  Future<void> openBillPayment(String service, BillPaymentPrefill prefill) {
    calls.add('openBillPayment:$service');
    return _show('Bill Payment ($service)', {
      'Biller': prefill.billerName,
      'Amount': _amount(prefill.amountPaisa),
    });
  }

  @override
  Future<void> openAutopay({String? service}) {
    calls.add('openAutopay${service == null ? '' : ':$service'}');
    return _show('Autopay', {'Service': service});
  }

  @override
  Future<void> openSmartDeposit({SmartDepositPrefill? prefill}) {
    calls.add('openSmartDeposit');
    return _show('Smart Deposit', {
      'Goal': prefill?.goalName,
      'Every month': _amount(prefill?.monthlyAmountPaisa),
    });
  }

  @override
  Future<bool> authenticate({required String reason}) async {
    calls.add('authenticate');
    final context = navigatorKey.currentContext;
    if (context == null) return false;
    final ok = await showModalBottomSheet<bool>(
      context: context,
      builder: (context) => _SheetBody(
        title: 'Would ask for MPIN / biometric',
        lines: {'Reason': reason},
        actions: [
          OutlinedButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Approve (mock)'),
          ),
        ],
      ),
    );
    return ok ?? false;
  }

  String? _amount(int? paisa) => paisa == null ? null : formatNpr(paisa);

  Future<void> _show(String flow, Map<String, String?> prefill) async {
    final context = navigatorKey.currentContext;
    if (context == null) return;
    await showModalBottomSheet<void>(
      context: context,
      builder: (context) => _SheetBody(
        title: 'Would open $flow',
        lines: prefill,
        actions: [
          FilledButton(onPressed: () => Navigator.of(context).pop(), child: const Text('OK')),
        ],
      ),
    );
  }
}

class _SheetBody extends StatelessWidget {
  const _SheetBody({required this.title, required this.lines, required this.actions});

  final String title;
  final Map<String, String?> lines;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) {
    final shown = lines.entries.where((e) => e.value != null && e.value!.isNotEmpty).toList();
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(OkaySpacing.xl, 0, OkaySpacing.xl, OkaySpacing.xl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(title, style: OkayText.sectionTitle),
            const SizedBox(height: OkaySpacing.xs),
            const Text(
              'Mock host app: the real Khalti flow opens here, pre-filled.',
              style: OkayText.subtitle,
            ),
            const SizedBox(height: OkaySpacing.lg),
            for (final e in shown)
              Padding(
                padding: const EdgeInsets.only(bottom: OkaySpacing.sm),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(e.key, style: OkayText.subtitle),
                    const SizedBox(width: OkaySpacing.md),
                    Expanded(
                      child: Text(e.value!, style: OkayText.body, textAlign: TextAlign.end),
                    ),
                  ],
                ),
              ),
            const SizedBox(height: OkaySpacing.lg),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                for (final (i, a) in actions.indexed) ...[
                  if (i > 0) const SizedBox(width: OkaySpacing.md),
                  a,
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }
}
