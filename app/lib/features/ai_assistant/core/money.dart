/// Money formatting. Amounts arrive from the API as integer paisa (Rs. 1 = 100 paisa).
library;

const _devanagariDigits = ['०', '१', '२', '३', '४', '५', '६', '७', '८', '९'];

/// Western digits -> Devanagari digits ('1,500' -> '१,५००').
String toNepaliDigits(String text) =>
    text.replaceAllMapped(RegExp(r'\d'), (m) => _devanagariDigits[int.parse(m[0]!)]);

/// '125000' -> '1,25,000': last three digits, then groups of two (Nepali/Indian style).
String groupLakh(String digits) {
  if (digits.length <= 3) return digits;
  var head = digits.substring(0, digits.length - 3);
  final tail = digits.substring(digits.length - 3);
  final groups = <String>[];
  while (head.length > 2) {
    groups.insert(0, head.substring(head.length - 2));
    head = head.substring(0, head.length - 2);
  }
  if (head.isNotEmpty) groups.insert(0, head);
  return '${groups.join(',')},$tail';
}

/// Formats paisa as rupees with lakh grouping. Matches the backend's `format_npr`.
///
///     formatNpr(12500050) == 'Rs. 1,25,000.50'
///     formatNpr(150000)   == 'Rs. 1,500'          (whole rupees drop .00)
///     formatNpr(150000, nepali: true) == 'रु. १,५००'
String formatNpr(int paisa, {bool alwaysDecimals = false, bool nepali = false}) {
  final sign = paisa < 0 ? '-' : '';
  final abs = paisa.abs();
  final rupees = abs ~/ 100;
  final p = abs % 100;
  var text = groupLakh(rupees.toString());
  if (p != 0 || alwaysDecimals) text += '.${p.toString().padLeft(2, '0')}';
  if (nepali) return '$signरु. ${toNepaliDigits(text)}';
  return '${sign}Rs. $text';
}

/// What a masked amount looks like when the user has hidden their balance.
String maskedNpr({bool nepali = false}) => nepali ? 'रु. ••••' : 'Rs. ••••';

/// What the user typed in an amount field -> paisa, or null if it isn't a positive amount.
/// Accepts "6000", "6,000", "1,25,000.50" and Devanagari digits ("६,०००").
int? parseRupees(String input) {
  var text = input.trim().replaceAll(RegExp(r'^(Rs\.?|रु\.?)\s*', caseSensitive: false), '');
  text = text.replaceAllMapped(RegExp('[०-९]'), (m) => '${'०१२३४५६७८९'.indexOf(m[0]!)}');
  text = text.replaceAll(RegExp(r'[,\s]'), '');
  final match = RegExp(r'^(\d{1,10})(?:\.(\d{1,2}))?$').firstMatch(text);
  if (match == null) return null;
  final paisa = int.parse(match[1]!) * 100 + int.parse((match[2] ?? '0').padRight(2, '0'));
  return paisa > 0 ? paisa : null;
}

/// Paisa -> the plain number to pre-fill an amount field with ('6000', '1140.67').
String rupeesInput(int paisa) =>
    paisa % 100 == 0 ? '${paisa ~/ 100}' : (paisa / 100).toStringAsFixed(2);
