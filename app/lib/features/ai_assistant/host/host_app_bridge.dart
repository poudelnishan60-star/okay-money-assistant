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

  /// Load money from the user's bank into the wallet.
  Future<void> openLoadMoney({int? amountPaisa});

  /// Move money from the wallet to the user's bank account.
  Future<void> openWithdrawToBank({int? amountPaisa});

  /// Request money from people, e.g. their share of a bill split by the assistant.
  Future<void> openRequestMoney(RequestMoneyPrefill prefill);

  /// Khalti support, with the transaction the problem is about attached when there is one.
  Future<void> openSupport(SupportPrefill prefill);

  /// Khalti's security screen, where the user blocks the wallet (lost phone, fraud).
  Future<void> openWalletSecurity();

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

@immutable
class RequestShare {
  const RequestShare(this.name, this.amountPaisa);
  final String name;
  final int amountPaisa;
}

/// One request ([recipientName], [amountPaisa]) or several ([requests]). For a split bill,
/// [totalPaisa] is the bill and [yourSharePaisa] the user's own part (it takes any leftover
/// paisa); the assistant worked the shares out in code.
@immutable
class RequestMoneyPrefill {
  const RequestMoneyPrefill({
    this.recipientName,
    this.amountPaisa,
    this.requests = const [],
    this.totalPaisa,
    this.yourSharePaisa,
  });
  final String? recipientName;
  final int? amountPaisa;
  final List<RequestShare> requests;
  final int? totalPaisa;
  final int? yourSharePaisa;
}

@immutable
class SupportPrefill {
  const SupportPrefill({this.transactionId, this.transactionLabel, this.issue});
  final String? transactionId;

  /// e.g. 'Nepal Telecom · Rs. 500 · 05 Nov 2026 · failed'
  final String? transactionLabel;
  final String? issue;
}

/// The host app MUST override this (the demo host uses MockHostAppBridge).
final hostAppBridgeProvider = Provider<HostAppBridge>(
  (ref) => throw UnimplementedError('Override hostAppBridgeProvider in the host app.'),
);
