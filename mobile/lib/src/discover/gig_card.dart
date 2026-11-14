import 'package:barterly/src/discover/gig.dart';
import 'package:barterly/src/theme/tokens.dart';
import 'package:barterly/src/widgets/feedback.dart';
import 'package:material_ui/material_ui.dart';

/// One gig in the discover list (design canvas: Main, "Gigs for you").
class GigCard extends StatelessWidget {
  const new({required this.gig, required this.onTap, super.key});

  final Gig gig;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final colors = payModelColors(gig.payModel);
    final terms = [?gig.workSummary, gig.youGet].join(' · ');
    return Semantics(
      button: true,
      label:
          '${gig.title}. ${gig.payModel?.label ?? ''}. '
          '${gig.fit.score}% fit. ${gig.property.place}. $terms. '
          '${gig.whenSummary}.',
      excludeSemantics: true,
      child: Material(
        color: BarterlyColors.surface,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(18),
          side: const BorderSide(color: BarterlyColors.border),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Stack(
                children: [
                  GigBanner(tint: colors.tint, height: 96),
                  Positioned(
                    left: 12,
                    top: 12,
                    child: Tag(
                      label: gig.payModel?.label ?? 'Gig',
                      background: colors.background,
                      foreground: colors.foreground,
                    ),
                  ),
                  Positioned(
                    right: 12,
                    top: 12,
                    child: Tag(label: '${gig.fit.score}% fit'),
                  ),
                ],
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(14, 12, 14, 14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  spacing: 6,
                  children: [
                    Text(
                      gig.title,
                      style: Theme.of(context).textTheme.titleLarge
                          ?.copyWith(fontSize: 17, height: 1.25),
                    ),
                    Row(
                      children: [
                        Icon(
                          gig.hostVerified
                              ? Icons.verified_user_outlined
                              : Icons.place_outlined,
                          size: 14,
                          color: BarterlyColors.accent,
                        ),
                        const SizedBox(width: 6),
                        Expanded(
                          child: Text(
                            gig.property.place,
                            style: const TextStyle(
                              fontSize: 13,
                              color: BarterlyColors.inkMuted,
                            ),
                          ),
                        ),
                      ],
                    ),
                    Text(terms, style: const TextStyle(fontSize: 13)),
                    Text(
                      gig.whenSummary,
                      style: const TextStyle(
                        fontSize: 13,
                        color: BarterlyColors.inkMuted,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
