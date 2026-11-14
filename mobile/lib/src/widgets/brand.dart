import 'package:barterly/src/theme/tokens.dart';
import 'package:material_ui/material_ui.dart';

/// The Barterly logo: an accent tile with a "b", and the word mark.
class BrandMark extends StatelessWidget {
  const new({super.key});

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: 'Barterly',
      excludeSemantics: true,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 32,
            height: 32,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: BarterlyColors.accent,
              borderRadius: BorderRadius.circular(10),
            ),
            child: Text(
              'b',
              style: Theme.of(context).textTheme.titleLarge
                  ?.copyWith(color: BarterlyColors.onAccent, height: 1),
            ),
          ),
          const SizedBox(width: BarterlySpace.sm),
          Text(
            'Barterly',
            style: Theme.of(context).textTheme.titleLarge
                ?.copyWith(fontWeight: FontWeight.w700),
          ),
        ],
      ),
    );
  }
}
