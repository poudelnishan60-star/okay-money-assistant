import 'package:flutter/material.dart';

import '../theme/okay_theme.dart';

/// Rounded (radius 24) surface card.
class OkayCard extends StatelessWidget {
  const OkayCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(OkaySpacing.lg),
    this.onTap,
    this.color = OkayColors.surface,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final VoidCallback? onTap;
  final Color color;

  @override
  Widget build(BuildContext context) {
    const radius = BorderRadius.all(Radius.circular(OkayRadii.card));
    return Material(
      color: color,
      borderRadius: radius,
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(padding: padding, child: child),
      ),
    );
  }
}

class SectionHeader extends StatelessWidget {
  const SectionHeader(this.title, {super.key, this.actionLabel, this.onAction});

  final String title;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: OkaySpacing.xl, bottom: OkaySpacing.md),
      child: Row(
        children: [
          Expanded(child: Text(title, style: OkayText.sectionTitle)),
          if (actionLabel != null) TextButton(onPressed: onAction, child: Text(actionLabel!)),
        ],
      ),
    );
  }
}

/// Rounded-square service tile (~64px): dark rose background, light pink line icon.
class ServiceIconTile extends StatelessWidget {
  const ServiceIconTile({
    super.key,
    required this.icon,
    required this.label,
    this.onTap,
    this.badge,
  });

  final IconData icon;
  final String label;
  final VoidCallback? onTap;

  /// Optional small label on the tile, e.g. 'New'.
  final String? badge;

  @override
  Widget build(BuildContext context) {
    const radius = BorderRadius.all(Radius.circular(OkayRadii.iconTile));
    return Semantics(
      button: true,
      label: label,
      excludeSemantics: true,
      child: InkWell(
        onTap: onTap,
        borderRadius: radius,
        child: SizedBox(
          width: 84,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Stack(
                clipBehavior: Clip.none,
                children: [
                  Container(
                    width: OkaySizes.iconTile,
                    height: OkaySizes.iconTile,
                    decoration: const BoxDecoration(
                      color: OkayColors.iconTileBackground,
                      borderRadius: radius,
                    ),
                    child: Icon(
                      icon,
                      size: OkaySizes.iconTileIcon,
                      color: OkayColors.iconTileForeground,
                    ),
                  ),
                  if (badge != null)
                    Positioned(
                      top: -6,
                      right: -10,
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                        decoration: const BoxDecoration(
                          color: OkayColors.gold,
                          borderRadius: BorderRadius.all(Radius.circular(OkayRadii.pill)),
                        ),
                        child: Text(
                          badge!,
                          style: OkayText.caption.copyWith(
                            color: Colors.black,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                    ),
                ],
              ),
              const SizedBox(height: OkaySpacing.sm),
              Text(
                label,
                style: OkayText.caption.copyWith(color: OkayColors.text),
                textAlign: TextAlign.center,
                maxLines: 2,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Menu-style row: line icon, title + grey subtitle, chevron.
class MenuRow extends StatelessWidget {
  const MenuRow({
    super.key,
    required this.icon,
    required this.title,
    this.subtitle,
    this.onTap,
    this.trailing,
  });

  final IconData icon;
  final String title;
  final String? subtitle;
  final VoidCallback? onTap;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: 64),
        child: Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: OkaySpacing.gutter,
            vertical: OkaySpacing.md,
          ),
          child: Row(
            children: [
              Icon(icon, color: OkayColors.text, size: 26),
              const SizedBox(width: OkaySpacing.lg),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(title, style: OkayText.rowTitle),
                    if (subtitle != null) ...[
                      const SizedBox(height: 2),
                      Text(subtitle!, style: OkayText.subtitle),
                    ],
                  ],
                ),
              ),
              trailing ?? const Icon(Icons.chevron_right_rounded, color: OkayColors.textSecondary),
            ],
          ),
        ),
      ),
    );
  }
}

/// Pill-shaped chip with a 1px border; blue outline when selected.
class PillChip extends StatelessWidget {
  const PillChip({super.key, required this.label, this.selected = false, this.onTap, this.icon});

  final String label;
  final bool selected;
  final VoidCallback? onTap;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    const radius = BorderRadius.all(Radius.circular(OkayRadii.pill));
    return Semantics(
      selected: selected,
      button: true,
      child: Material(
        color: OkayColors.background,
        shape: StadiumBorder(
          side: BorderSide(
            color: selected ? OkayColors.chipSelected : OkayColors.chipBorder,
            width: selected ? 1.5 : 1,
          ),
        ),
        child: InkWell(
          onTap: onTap,
          borderRadius: radius,
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 40),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: OkaySpacing.lg),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (icon != null) ...[
                    Icon(icon, size: 16, color: OkayColors.text),
                    const SizedBox(width: OkaySpacing.xs),
                  ],
                  Text(
                    label,
                    style: OkayText.subtitle.copyWith(
                      color: OkayColors.text,
                      fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Transaction-list period filter.
enum PeriodChoice {
  days7('7 days', '7d'),
  days14('14 days', '14d'),
  days30('30 days', '30d'),
  thisMonth('This month', 'this_month'),
  custom('Custom', null);

  const PeriodChoice(this.label, this.apiValue);
  final String label;

  /// Value for GET /transactions?period=..., or null for a custom start/end.
  final String? apiValue;
}

class PeriodChips extends StatelessWidget {
  const PeriodChips({super.key, required this.selected, required this.onChanged});

  final PeriodChoice selected;
  final ValueChanged<PeriodChoice> onChanged;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.symmetric(horizontal: OkaySpacing.gutter),
      child: Row(
        children: [
          for (final (i, p) in PeriodChoice.values.indexed) ...[
            if (i > 0) const SizedBox(width: OkaySpacing.sm),
            PillChip(
              label: p.label,
              selected: p == selected,
              icon: p == PeriodChoice.custom ? Icons.calendar_today_outlined : null,
              onTap: () => onChanged(p),
            ),
          ],
        ],
      ),
    );
  }
}

/// Budget colour rule: green under 80%, amber 80-100%, red over 100%.
Color budgetColor(double percentUsed) {
  if (percentUsed > 100) return OkayColors.danger;
  if (percentUsed >= 80) return OkayColors.warning;
  return OkayColors.positive;
}

class BudgetProgressBar extends StatelessWidget {
  const BudgetProgressBar({super.key, required this.percentUsed, this.height = 10});

  final double percentUsed;
  final double height;

  @override
  Widget build(BuildContext context) {
    final fraction = (percentUsed / 100).clamp(0.0, 1.0);
    return Semantics(
      label: '${percentUsed.toStringAsFixed(0)} percent used',
      child: ClipRRect(
        borderRadius: BorderRadius.circular(height),
        child: SizedBox(
          height: height,
          child: Stack(
            fit: StackFit.expand,
            children: [
              const ColoredBox(color: OkayColors.surfaceElevated),
              FractionallySizedBox(
                alignment: Alignment.centerLeft,
                widthFactor: fraction,
                child: ColoredBox(color: budgetColor(percentUsed)),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
