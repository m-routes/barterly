import 'package:flutter/painting.dart';

/// Barterly design tokens, the same values as web/src/app/globals.css.
///
/// Contrast (WCAG 2.1 AA) on [ground]: ink 14.0:1, inkMuted 6.1:1,
/// accent 6.1:1, danger 6.9:1, fieldBorder 3.6:1; white on accent 6.4:1.
abstract final class BarterlyColors {
  static const ground = Color(0xFFFBF8F3);
  static const ink = Color(0xFF1F2A24);
  static const accent = Color(0xFF0F6B5C);

  static const surface = Color(0xFFFFFFFF);
  static const surfaceSunken = Color(0xFFF3EEE5);
  static const inkMuted = Color(0xFF56615A);
  static const accentSoft = Color(0xFFE2EFEB);
  static const onAccent = Color(0xFFFFFFFF);
  static const border = Color(0xFFE3DCCF);
  static const fieldBorder = Color(0xFF7E847B);
  static const danger = Color(0xFFA4262C);
  static const dangerSoft = Color(0xFFFBEAEA);
}

abstract final class BarterlySpace {
  static const xs = 4.0;
  static const sm = 8.0;
  static const md = 12.0;
  static const lg = 16.0;
  static const xl = 24.0;
  static const xxl = 32.0;
}

abstract final class BarterlyRadius {
  static const sm = 8.0;
  static const md = 12.0;
  static const lg = 20.0;
}

/// Minimum touch target: Material's 48dp, which also covers web's 44px rule.
const double minTouchTarget = 48;

const headingFont = 'Space Grotesk';
const bodyFont = 'Inter';
