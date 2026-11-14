import 'package:barterly/src/discover/gig.dart' show shortDate;
import 'package:barterly/src/pay_model.dart';
import 'package:barterly/src/theme/tokens.dart';
import 'package:intl/intl.dart';
import 'package:material_ui/material_ui.dart';

/// Grey placeholder shapes while content loads. Static rather than shimmering:
/// cheaper, calmer, and respects reduced motion without extra code.
class SkeletonBox extends StatelessWidget {
  const new({
    this.width,
    this.height = 14,
    this.radius = BarterlyRadius.sm,
    super.key,
  });

  final double? width;
  final double height;
  final double radius;

  @override
  Widget build(BuildContext context) => Container(
    width: width,
    height: height,
    decoration: BoxDecoration(
      color: BarterlyColors.surfaceSunken,
      borderRadius: BorderRadius.circular(radius),
    ),
  );
}

/// A list of [count] skeleton cards, announced once to screen readers.
class SkeletonList extends StatelessWidget {
  const new({
    required this.label,
    this.count = 3,
    this.itemBuilder,
    this.padding = const EdgeInsets.fromLTRB(20, 12, 20, 24),
    super.key,
  });

  final String label;
  final int count;
  final WidgetBuilder? itemBuilder;
  final EdgeInsets padding;

  @override
  Widget build(BuildContext context) => Semantics(
    liveRegion: true,
    label: label,
    child: ExcludeSemantics(
      child: ListView.separated(
        // Pull to refresh still works on the skeleton.
        physics: const AlwaysScrollableScrollPhysics(),
        padding: padding,
        itemCount: count,
        separatorBuilder: (_, _) => const SizedBox(height: 14),
        itemBuilder: (context, _) =>
            itemBuilder?.call(context) ?? const SkeletonCard(),
      ),
    ),
  );
}

class SkeletonCard extends StatelessWidget {
  const new({super.key});

  @override
  Widget build(BuildContext context) => const SurfaceCard(
    padding: EdgeInsets.zero,
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SkeletonBox(height: 96, radius: 0),
        Padding(
          padding: EdgeInsets.fromLTRB(14, 12, 14, 14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            spacing: 8,
            children: [
              SkeletonBox(width: 220, height: 18),
              SkeletonBox(width: 160),
              SkeletonBox(width: 240),
            ],
          ),
        ),
      ],
    ),
  );
}

/// White rounded card with the design's hairline border.
class SurfaceCard extends StatelessWidget {
  const new({
    required this.child,
    this.padding = const EdgeInsets.all(BarterlySpace.md),
    this.color = BarterlyColors.surface,
    this.radius = 18,
    super.key,
  });

  final Widget child;
  final EdgeInsets padding;
  final Color color;
  final double radius;

  @override
  Widget build(BuildContext context) => Material(
    // Material (not a decorated box) so list tiles inside can paint ink.
    color: color,
    clipBehavior: Clip.antiAlias,
    shape: RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(radius),
      side: const BorderSide(color: BarterlyColors.border),
    ),
    child: Padding(padding: padding, child: child),
  );
}

/// "You're offline" strip above content shown from the device's copy.
class OfflineBanner extends StatelessWidget {
  const new({required this.message, this.onRetry, super.key});

  final String message;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) => Semantics(
    liveRegion: true,
    child: Material(
      color: BarterlyColors.ink,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 4, 4, 4),
        child: Row(
          children: [
            const Icon(
              Icons.cloud_off_outlined,
              size: 18,
              color: BarterlyColors.ground,
            ),
            const SizedBox(width: BarterlySpace.sm),
            Expanded(
              child: Text(
                message,
                style: const TextStyle(
                  color: BarterlyColors.ground,
                  fontSize: 13,
                ),
              ),
            ),
            if (onRetry != null)
              TextButton(
                onPressed: onRetry,
                style: TextButton.styleFrom(
                  foregroundColor: BarterlyColors.ground,
                ),
                child: const Text('Retry'),
              ),
          ],
        ),
      ),
    ),
  );
}

/// "Saved 14 Nov, 09:30" for offline copies.
String savedAtLabel(DateTime when, {DateTime? now}) {
  final today = now ?? DateTime.now();
  final sameDay =
      when.year == today.year &&
      when.month == today.month &&
      when.day == today.day;
  final time = DateFormat('HH:mm').format(when);
  return sameDay ? 'today at $time' : '${shortDate(when)} at $time';
}

/// Small rounded label (pay model, fit, badges).
class Tag extends StatelessWidget {
  const new({
    required this.label,
    this.background = BarterlyColors.surface,
    this.foreground = BarterlyColors.ink,
    this.icon,
    this.outlined = false,
    super.key,
  });

  final String label;
  final Color background;
  final Color foreground;
  final IconData? icon;
  final bool outlined;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
    decoration: BoxDecoration(
      color: background,
      borderRadius: BorderRadius.circular(12),
      border: outlined ? Border.all(color: BarterlyColors.chipBorder) : null,
    ),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (icon != null) ...[
          Icon(icon, size: 13, color: foreground),
          const SizedBox(width: 4),
        ],
        Text(
          label,
          style: TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w600,
            color: foreground,
          ),
        ),
      ],
    ),
  );
}

/// The pay model's colours on the design canvas.
({Color background, Color foreground, Color tint}) payModelColors(
  PayModel? model,
) => switch (model) {
  PayModel.volunteer => (
    background: const Color(0xFFDDF0EA),
    foreground: const Color(0xFF0B4F43),
    tint: const Color(0xFFBFE0D6),
  ),
  PayModel.barter => (
    background: const Color(0xFFFBE9CF),
    foreground: const Color(0xFF6B3F05),
    tint: const Color(0xFFF3D3A6),
  ),
  PayModel.hybrid => (
    background: const Color(0xFFE6E3F7),
    foreground: const Color(0xFF3A2F8A),
    tint: const Color(0xFFCFCBEF),
  ),
  PayModel.paid || null => (
    background: const Color(0xFFE1EAF6),
    foreground: const Color(0xFF1E3A6B),
    tint: const Color(0xFFC6D6EC),
  ),
};

/// The soft mountain shapes over a gig's colour band.
class GigBanner extends StatelessWidget {
  const new({required this.tint, required this.height, super.key});

  final Color tint;
  final double height;

  @override
  Widget build(BuildContext context) => SizedBox(
    height: height,
    width: double.infinity,
    child: CustomPaint(painter: _HillsPainter(tint)),
  );
}

class _HillsPainter extends CustomPainter {
  new(this.tint);

  final Color tint;

  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawRect(Offset.zero & size, Paint()..color = tint);
    final w = size.width;
    final h = size.height;
    Path hills(List<Offset> points) {
      final path = Path()..moveTo(0, h);
      for (final p in points) {
        path.lineTo(p.dx * w, p.dy * h);
      }
      return path
        ..lineTo(w, h)
        ..close();
    }

    canvas
      ..drawPath(
        hills(const [
          Offset(0, .65),
          Offset(.14, .3),
          Offset(.26, .6),
          Offset(.42, .17),
          Offset(.59, .65),
          Offset(.74, .33),
          Offset(1, .68),
        ]),
        Paint()..color = const Color(0x73FFFFFF),
      )
      ..drawPath(
        hills(const [
          Offset(0, .81),
          Offset(.18, .54),
          Offset(.34, .79),
          Offset(.54, .42),
          Offset(.8, .81),
          Offset(1, .81),
        ]),
        Paint()..color = const Color(0x99FFFFFF),
      );
  }

  @override
  bool shouldRepaint(_HillsPainter oldDelegate) => oldDelegate.tint != tint;
}
