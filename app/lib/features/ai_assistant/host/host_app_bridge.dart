import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// The ONLY way the assistant reaches into the Khalti app. The assistant never moves money:
/// it opens the app's existing flow pre-filled, and the user finishes it with MPIN/biometric.
abstract interface class HostAppBridge {
  Future<void> openSendMoney(SendMoneyPrefill prefill);

  /// [service] is the backend's service id, e.g. 'electricity', 'khanepani', 'internet',
  /// 'tv', 'data_pack', 'mobile_topup'.
  Future<void> openBillPayment(String service, BillPaymentPrefill prefill);

  Future<void> openAutopay({String? service});

  Future<void> openSmartDeposit({SmartDepositPrefill? prefill});

  /// Asks the host to verify the user (MPIN / biometric). True if verified.
  Future<bool> authenticate({required String reason});
}

@immutable
class SendMoneyPrefill {
  const SendMoneyPrefill({this.recipientName, this.amountPaisa, this.note});
  final String? recipientName;
  final int? amountPaisa;
  final String? note;
}

@immutable
class BillPaymentPrefill {
  const BillPaymentPrefill({this.billerName, this.amountPaisa});
  final String? billerName;
  final int? amountPaisa;
}

@immutable
class SmartDepositPrefill {
  const SmartDepositPrefill({this.goalName, this.monthlyAmountPaisa});
  final String? goalName;
  final int? monthlyAmountPaisa;
}

/// The host app MUST override this (the demo host uses MockHostAppBridge).
final hostAppBridgeProvider = Provider<HostAppBridge>(
  (ref) => throw UnimplementedError('Override hostAppBridgeProvider in the host app.'),
);
