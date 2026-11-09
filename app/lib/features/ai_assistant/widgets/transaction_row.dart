import 'package:flutter/material.dart';

import '../core/dates.dart';
import '../theme/okay_theme.dart';
import 'amount_text.dart';

/// Icon and title for a backend transaction type / service.
({IconData icon, String title}) transactionVisual(String type, String? service) {
  switch (service) {
    case 'electricity':
      return (icon: Icons.bolt_outlined, title: 'Electricity Payment');
    case 'khanepani':
      return (icon: Icons.water_drop_outlined, title: 'Khanepani Payment');
    case 'internet':
      return (icon: Icons.wifi_outlined, title: 'Internet Payment');
    case 'tv':
      return (icon: Icons.tv_outlined, title: 'TV Payment');
    case 'data_pack':
      return (icon: Icons.signal_cellular_alt_outlined, title: 'Data Pack');
    case 'mobile_topup':
      return (icon: Icons.phone_android_outlined, title: 'Mobile Topup');
    case 'bus':
      return (icon: Icons.directions_bus_outlined, title: 'Bus Ticket');
    case 'flight':
      return (icon: Icons.flight_outlined, title: 'Flight Ticket');
    case 'hotel':
      return (icon: Icons.hotel_outlined, title: 'Hotel Booking');
    case 'movie':
      return (icon: Icons.movie_outlined, title: 'Movie Ticket');
    case 'smart_deposit':
      return (icon: Icons.savings_outlined, title: 'Smart Deposit');
    case 'bank_load':
      return (icon: Icons.account_balance_outlined, title: 'Load Fund');
  }
  return switch (type) {
    'scan_pay' => (icon: Icons.qr_code_scanner_outlined, title: 'Scan and Pay'),
    'bill_payment' => (icon: Icons.receipt_long_outlined, title: 'Bill Payment'),
    'topup' => (icon: Icons.phone_android_outlined, title: 'Topup'),
    'transfer' => (icon: Icons.swap_horiz_outlined, title: 'Fund Transfer'),
    'remittance' => (icon: Icons.public_outlined, title: 'Remittance Received'),
    'booking' => (icon: Icons.confirmation_number_outlined, title: 'Booking'),
    'deposit' => (icon: Icons.savings_outlined, title: 'Deposit'),
    _ => (icon: Icons.receipt_outlined, title: 'Transaction'),
  };
}

/// One transaction: type icon, title, 'merchant | reference', time, amount with arrow.
class TransactionRow extends StatelessWidget {
  const TransactionRow({
    super.key,
    required this.icon,
    required this.title,
    required this.merchant,
    required this.nepalTime,
    required this.amountPaisa,
    required this.isDebit,
    this.reference,
    this.onTap,
  });

  final IconData icon;
  final String title;
  final String merchant;
  final String? reference;
  final DateTime nepalTime;
  final int amountPaisa;
  final bool isDebit;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final sub = reference == null ? merchant : '$merchant | $reference';
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: OkaySpacing.gutter,
          vertical: OkaySpacing.md,
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 44,
              height: 44,
              decoration: const BoxDecoration(
                color: OkayColors.iconTileBackground,
                borderRadius: BorderRadius.all(Radius.circular(14)),
              ),
              child: Icon(icon, color: OkayColors.iconTileForeground, size: 22),
            ),
            const SizedBox(width: OkaySpacing.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: OkayText.body.copyWith(fontWeight: FontWeight.w500)),
                  const SizedBox(height: 2),
                  Text(sub, style: OkayText.subtitle, maxLines: 1, overflow: TextOverflow.ellipsis),
                  const SizedBox(height: 2),
                  Text(formatTime(nepalTime), style: OkayText.caption),
                ],
              ),
            ),
            const SizedBox(width: OkaySpacing.sm),
            AmountText(amountPaisa, isDebit: isDebit, showArrow: true),
          ],
        ),
      ),
    );
  }
}

/// Day header of the transaction list: big day number, weekday + 'Mon YYYY', closing balance.
class DateGroupHeader extends StatelessWidget {
  const DateGroupHeader({
    super.key,
    required this.date,
    required this.closingBalancePaisa,
    this.calendar = CalendarSystem.ad,
  });

  final DateTime date;
  final int? closingBalancePaisa;
  final CalendarSystem calendar;

  @override
  Widget build(BuildContext context) {
    final parts = dayHeaderParts(date, calendar);
    return Container(
      color: OkayColors.background,
      padding: const EdgeInsets.fromLTRB(
        OkaySpacing.gutter,
        OkaySpacing.lg,
        OkaySpacing.gutter,
        OkaySpacing.sm,
      ),
      child: Row(
        children: [
          Text(parts.day, style: OkayText.bigNumber),
          const SizedBox(width: OkaySpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(parts.weekday, style: OkayText.body.copyWith(fontWeight: FontWeight.w500)),
                Text(parts.monthYear, style: OkayText.subtitle),
              ],
            ),
          ),
          if (closingBalancePaisa != null)
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                const Text('Closing Balance', style: OkayText.caption),
                AmountText(closingBalancePaisa!, style: OkayText.amount.copyWith(fontSize: 15)),
              ],
            ),
        ],
      ),
    );
  }
}
