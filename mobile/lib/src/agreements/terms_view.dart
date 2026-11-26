import 'package:barterly/src/agreements/terms.dart';
import 'package:barterly/src/theme/tokens.dart';
import 'package:barterly/src/widgets/feedback.dart';
import 'package:material_ui/material_ui.dart';

/// Terms as label/value rows; rows in [changed] carry a "Changed" tag.
class TermsView extends StatelessWidget {
  const new({required this.terms, this.changed = const [], super.key});

  final Terms terms;
  final List<String> changed;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    spacing: BarterlySpace.sm,
    children: [
      for (final (field, label, value) in terms.rows())
        _Row(label: label, value: value, changed: rowChanged(field, changed)),
    ],
  );
}

class _Row extends StatelessWidget {
  const new({required this.label, required this.value, required this.changed});

  final String label;
  final String value;
  final bool changed;

  @override
  Widget build(BuildContext context) => Container(
    padding: changed ? const EdgeInsets.only(left: BarterlySpace.sm) : null,
    decoration: changed
        ? const BoxDecoration(
            border: Border(
              left: BorderSide(color: BarterlyColors.accent, width: 3),
            ),
          )
        : null,
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      spacing: 2,
      children: [
        Wrap(
          spacing: BarterlySpace.sm,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            Text(
              label,
              style: const TextStyle(
                fontSize: 13,
                color: BarterlyColors.inkMuted,
              ),
            ),
            if (changed)
              const Tag(
                label: 'Changed',
                background: BarterlyColors.accentSoft,
                foreground: BarterlyColors.onAccentSoft,
              ),
          ],
        ),
        Text(value),
      ],
    ),
  );
}
