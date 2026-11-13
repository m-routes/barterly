import 'package:barterly/src/theme/tokens.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:material_ui/material_ui.dart';

/// The app's Material theme, built from [BarterlyColors].
///
/// [brandFonts] loads Space Grotesk and Inter through google_fonts. Tests pass
/// false so nothing is fetched over the network.
ThemeData barterlyTheme({bool brandFonts = true}) {
  const scheme = ColorScheme(
    brightness: Brightness.light,
    primary: BarterlyColors.accent,
    onPrimary: BarterlyColors.onAccent,
    primaryContainer: BarterlyColors.accentSoft,
    onPrimaryContainer: BarterlyColors.accent,
    secondary: BarterlyColors.accent,
    onSecondary: BarterlyColors.onAccent,
    error: BarterlyColors.danger,
    onError: BarterlyColors.onAccent,
    errorContainer: BarterlyColors.dangerSoft,
    onErrorContainer: BarterlyColors.danger,
    surface: BarterlyColors.ground,
    onSurface: BarterlyColors.ink,
    onSurfaceVariant: BarterlyColors.inkMuted,
    surfaceContainerLowest: BarterlyColors.surface,
    surfaceContainerLow: BarterlyColors.surface,
    surfaceContainer: BarterlyColors.surface,
    surfaceContainerHigh: BarterlyColors.surfaceSunken,
    outline: BarterlyColors.fieldBorder,
    outlineVariant: BarterlyColors.border,
  );

  final base = ThemeData(colorScheme: scheme, useMaterial3: true);
  var text = base.textTheme.apply(
    bodyColor: BarterlyColors.ink,
    displayColor: BarterlyColors.ink,
  );
  if (brandFonts) {
    text = GoogleFonts.interTextTheme(text);
    final headings = GoogleFonts.spaceGroteskTextTheme(text);
    text = text.copyWith(
      displayLarge: headings.displayLarge,
      displayMedium: headings.displayMedium,
      displaySmall: headings.displaySmall,
      headlineLarge: headings.headlineLarge,
      headlineMedium: headings.headlineMedium,
      headlineSmall: headings.headlineSmall,
      titleLarge: headings.titleLarge,
    );
  }
  text = text.copyWith(
    headlineMedium: text.headlineMedium?.copyWith(fontWeight: FontWeight.w700),
    headlineSmall: text.headlineSmall?.copyWith(fontWeight: FontWeight.w700),
    titleLarge: text.titleLarge?.copyWith(fontWeight: FontWeight.w600),
  );

  const minSize = Size(minTouchTarget, minTouchTarget);
  final pill = RoundedRectangleBorder(borderRadius: BorderRadius.circular(999));
  OutlineInputBorder field(Color color, [double width = 1.5]) =>
      OutlineInputBorder(
        borderRadius: BorderRadius.circular(BarterlyRadius.sm),
        borderSide: BorderSide(color: color, width: width),
      );

  return base.copyWith(
    scaffoldBackgroundColor: BarterlyColors.ground,
    textTheme: text,
    materialTapTargetSize: MaterialTapTargetSize.padded,
    appBarTheme: AppBarTheme(
      backgroundColor: BarterlyColors.ground,
      foregroundColor: BarterlyColors.ink,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      titleTextStyle: text.titleLarge,
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: minSize,
        shape: pill,
        padding: const EdgeInsets.symmetric(horizontal: BarterlySpace.xl),
        textStyle: text.labelLarge?.copyWith(fontWeight: FontWeight.w600),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: minSize,
        shape: pill,
        side: const BorderSide(color: BarterlyColors.accent, width: 2),
        foregroundColor: BarterlyColors.accent,
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(minimumSize: minSize),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: BarterlyColors.surface,
      border: field(BarterlyColors.fieldBorder),
      enabledBorder: field(BarterlyColors.fieldBorder),
      focusedBorder: field(BarterlyColors.accent, 2),
      errorBorder: field(BarterlyColors.danger),
      focusedErrorBorder: field(BarterlyColors.danger, 2),
      errorStyle: const TextStyle(color: BarterlyColors.danger),
      helperStyle: const TextStyle(color: BarterlyColors.inkMuted),
      floatingLabelBehavior: FloatingLabelBehavior.always,
      contentPadding: const EdgeInsets.symmetric(
        horizontal: BarterlySpace.md,
        vertical: BarterlySpace.md,
      ),
    ),
    chipTheme: base.chipTheme.copyWith(
      selectedColor: BarterlyColors.accentSoft,
      checkmarkColor: BarterlyColors.accent,
      side: const BorderSide(color: BarterlyColors.fieldBorder),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(BarterlyRadius.sm),
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: BarterlyColors.surface,
      indicatorColor: BarterlyColors.accentSoft,
      surfaceTintColor: Colors.transparent,
      iconTheme: WidgetStateProperty.resolveWith(
        (states) => IconThemeData(
          color: states.contains(WidgetState.selected)
              ? BarterlyColors.accent
              : BarterlyColors.inkMuted,
        ),
      ),
      labelTextStyle: WidgetStateProperty.resolveWith(
        (states) => text.labelMedium?.copyWith(
          color: states.contains(WidgetState.selected)
              ? BarterlyColors.accent
              : BarterlyColors.inkMuted,
          fontWeight: states.contains(WidgetState.selected)
              ? FontWeight.w600
              : FontWeight.w500,
        ),
      ),
    ),
    snackBarTheme: const SnackBarThemeData(
      backgroundColor: BarterlyColors.ink,
      contentTextStyle: TextStyle(color: BarterlyColors.ground),
      behavior: SnackBarBehavior.floating,
    ),
    dividerTheme: const DividerThemeData(color: BarterlyColors.border),
  );
}
