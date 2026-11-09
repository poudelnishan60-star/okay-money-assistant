import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Balance privacy. If the user hid their balance in the host app, every amount on the
/// assistant screens is masked until they tap one; tapping reveals all of them for the session.
@immutable
class AmountPrivacy {
  const AmountPrivacy({this.hiddenByUser = false, this.revealed = false});

  /// The host app's "hide balance" setting.
  final bool hiddenByUser;

  /// The user tapped a masked amount on an assistant screen.
  final bool revealed;

  bool get masked => hiddenByUser && !revealed;
}

class AmountPrivacyNotifier extends Notifier<AmountPrivacy> {
  @override
  AmountPrivacy build() => const AmountPrivacy();

  /// Called by the host whenever its eye toggle changes. Re-hiding also forgets "revealed".
  void setHiddenByUser(bool hidden) => state = AmountPrivacy(hiddenByUser: hidden);

  void reveal() {
    if (state.masked) {
      state = AmountPrivacy(hiddenByUser: state.hiddenByUser, revealed: true);
    }
  }
}

final amountPrivacyProvider = NotifierProvider<AmountPrivacyNotifier, AmountPrivacy>(
  AmountPrivacyNotifier.new,
);
