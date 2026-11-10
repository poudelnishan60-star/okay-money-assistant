// All design tokens for the O-Kay assistant live in this one file, so they can be mapped onto
// the Khalti app's design system when the feature is merged.
//
// Hex values are APPROXIMATE (read off the current app); replace them with official tokens.

import 'package:flutter/material.dart';

/// Colours (dark theme, v1).
abstract final class OkayColors {
  static const background = Color(0xFF121212);
  static const chatBackground = Color(0xFF000000);
  static const surface = Color(0xFF1E1E1E);
  static const surfaceElevated = Color(0xFF262626);
  static const divider = Color(0xFF2A2A2A);

  /// Quick-action icons, main buttons, the centre Scan & Pay button.
  static const primary = Color(0xFFC8102E);
  static const userBubble = Color(0xFF7A1515);
  static const assistantBubble = Color(0xFF222222);

  /// Active tab, debit arrows.
  static const accentPink = Color(0xFFF0507A);

  /// Service icon tiles: dark rose square with light pink line icon.
  static const iconTileBackground = Color(0xFF3A1A20);
  static const iconTileForeground = Color(0xFFF5B5C3);

  /// Rewards, mascot glow, insight highlights.
  static const gold = Color(0xFFF5B700);

  /// Outline of a selected filter chip.
  static const chipSelected = Color(0xFF3B82F6);
  static const chipBorder = Color(0xFF3A3A3A);

  static const positive = Color(0xFF22C55E);
  static const warning = Color(0xFFF59E0B);

  /// Over-budget red. Not in the spec's palette; chosen to differ from the brand red.
  static const danger = Color(0xFFEF4444);

  static const text = Color(0xFFFFFFFF);
  static const textSecondary = Color(0xFF9E9E9E);
}

/// Chart colours. Single-series charts use [single]. The category donut uses [categorical] in
/// this fixed order (never cycled) and folds the rest into [other]. Validated as a set on the
/// dark card surface #1E1E1E: lightness band, chroma, colour-blind separation of neighbours
/// (worst ΔE 8.4) incl. the last-next-to-first pair on a ring, and >= 3:1 contrast.
abstract final class OkayChartColors {
  static const single = OkayColors.accentPink;
  static const categorical = <Color>[
    Color(0xFF3987E5), // blue
    Color(0xFFD95926), // orange
    Color(0xFF199E70), // aqua
    Color(0xFFC98500), // yellow
    Color(0xFFD55181), // magenta
  ];
  static const other = Color(0xFF7A7A7A);
}

abstract final class OkayRadii {
  static const double card = 24;
  static const double iconTile = 18;
  static const double bubble = 20;
  static const double pill = 999;
}

abstract final class OkaySizes {
  static const double iconTile = 64;
  static const double iconTileIcon = 28;
  static const double minTouchTarget = 48;
  static const double scanPayButton = 64;
}

abstract final class OkaySpacing {
  static const double xs = 4;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 24;
  static const double xxl = 32;

  /// Side gutter of every assistant screen.
  static const double gutter = 16;
}

/// Typography. DM Sans with Noto Sans Devanagari as the Nepali fallback. If the font files
/// are not bundled, Flutter falls back to the platform font (Roboto + system Noto on Android).
abstract final class OkayText {
  static const fontFamily = 'DM Sans';
  static const fontFallback = <String>['Noto Sans Devanagari'];

  static const pageTitle = TextStyle(
    fontFamily: fontFamily,
    fontFamilyFallback: fontFallback,
    fontSize: 30,
    height: 1.2,
    fontWeight: FontWeight.w700,
    color: OkayColors.text,
  );
  static const sectionTitle = TextStyle(
    fontFamily: fontFamily,
    fontFamilyFallback: fontFallback,
    fontSize: 20,
    height: 1.3,
    fontWeight: FontWeight.w700,
    color: OkayColors.text,
  );
  static const rowTitle = TextStyle(
    fontFamily: fontFamily,
    fontFamilyFallback: fontFallback,
    fontSize: 18,
    height: 1.3,
    fontWeight: FontWeight.w500,
    color: OkayColors.text,
  );
  static const body = TextStyle(
    fontFamily: fontFamily,
    fontFamilyFallback: fontFallback,
    fontSize: 16,
    height: 1.4,
    fontWeight: FontWeight.w400,
    color: OkayColors.text,
  );
  static const subtitle = TextStyle(
    fontFamily: fontFamily,
    fontFamilyFallback: fontFallback,
    fontSize: 14,
    height: 1.35,
    fontWeight: FontWeight.w400,
    color: OkayColors.textSecondary,
  );
  static const caption = TextStyle(
    fontFamily: fontFamily,
    fontFamilyFallback: fontFallback,
    fontSize: 12,
    height: 1.3,
    fontWeight: FontWeight.w400,
    color: OkayColors.textSecondary,
  );
  static const amount = TextStyle(
    fontFamily: fontFamily,
    fontFamilyFallback: fontFallback,
    fontSize: 16,
    height: 1.3,
    fontWeight: FontWeight.w600,
    color: OkayColors.text,
    fontFeatures: [FontFeature.tabularFigures()],
  );
  static const bigNumber = TextStyle(
    fontFamily: fontFamily,
    fontFamilyFallback: fontFallback,
    fontSize: 32,
    height: 1.1,
    fontWeight: FontWeight.w700,
    color: OkayColors.text,
    fontFeatures: [FontFeature.tabularFigures()],
  );
}

/// Placeholder slots for brand assets. Real files go in app/assets/okay/ (not drawn here).
abstract final class OkayAssets {
  static const mascot = 'assets/okay/mascot.png';
  static const mascotAvatar = 'assets/okay/mascot_avatar.png';
}

ThemeData buildOkayTheme() {
  const scheme = ColorScheme.dark(
    primary: OkayColors.primary,
    onPrimary: OkayColors.text,
    secondary: OkayColors.accentPink,
    onSecondary: OkayColors.text,
    tertiary: OkayColors.gold,
    surface: OkayColors.surface,
    onSurface: OkayColors.text,
    surfaceContainerHighest: OkayColors.surfaceElevated,
    outline: OkayColors.chipBorder,
    outlineVariant: OkayColors.divider,
    error: OkayColors.danger,
  );
  final base = ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    colorScheme: scheme,
    scaffoldBackgroundColor: OkayColors.background,
    fontFamily: OkayText.fontFamily,
    fontFamilyFallback: OkayText.fontFallback,
  );
  const pill = StadiumBorder();
  return base.copyWith(
    textTheme: base.textTheme.apply(bodyColor: OkayColors.text, displayColor: OkayColors.text),
    appBarTheme: const AppBarTheme(
      backgroundColor: OkayColors.background,
      foregroundColor: OkayColors.text,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: false,
      titleTextStyle: OkayText.rowTitle,
    ),
    dividerTheme: const DividerThemeData(color: OkayColors.divider, thickness: 1, space: 1),
    cardTheme: const CardThemeData(
      color: OkayColors.surface,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.all(Radius.circular(OkayRadii.card)),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: OkayColors.primary,
        foregroundColor: OkayColors.text,
        minimumSize: const Size(64, OkaySizes.minTouchTarget),
        shape: pill,
        textStyle: OkayText.body.copyWith(fontWeight: FontWeight.w600),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: OkayColors.text,
        minimumSize: const Size(64, OkaySizes.minTouchTarget),
        side: const BorderSide(color: OkayColors.chipBorder),
        shape: pill,
        textStyle: OkayText.body.copyWith(fontWeight: FontWeight.w600),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(foregroundColor: OkayColors.accentPink),
    ),
    inputDecorationTheme: const InputDecorationTheme(
      filled: true,
      fillColor: OkayColors.surface,
      hintStyle: OkayText.subtitle,
      contentPadding: EdgeInsets.symmetric(horizontal: 20, vertical: 14),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.all(Radius.circular(OkayRadii.pill)),
        borderSide: BorderSide(color: OkayColors.chipBorder),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.all(Radius.circular(OkayRadii.pill)),
        borderSide: BorderSide(color: OkayColors.chipBorder),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.all(Radius.circular(OkayRadii.pill)),
        borderSide: BorderSide(color: OkayColors.textSecondary),
      ),
    ),
    bottomSheetTheme: const BottomSheetThemeData(
      backgroundColor: OkayColors.surface,
      showDragHandle: true,
      dragHandleColor: OkayColors.chipBorder,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(OkayRadii.card)),
      ),
    ),
    snackBarTheme: const SnackBarThemeData(
      backgroundColor: OkayColors.surfaceElevated,
      contentTextStyle: OkayText.body,
      behavior: SnackBarBehavior.floating,
    ),
    progressIndicatorTheme: const ProgressIndicatorThemeData(color: OkayColors.accentPink),
  );
}
