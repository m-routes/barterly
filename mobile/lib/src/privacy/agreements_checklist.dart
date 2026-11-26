import 'package:barterly/src/privacy/legal.dart';
import 'package:barterly/src/privacy/legal_links.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

/// The separate, explicit agreements asked for at sign-up (and again when a
/// document changes). Each has its own checkbox; nothing is pre-ticked.
class AgreementsChecklist extends ConsumerWidget {
  const new({
    required this.terms,
    required this.privacy,
    required this.onTerms,
    required this.onPrivacy,
    this.adult,
    this.onAdult,
    super.key,
  });

  final bool? adult;
  final bool terms;
  final bool privacy;
  final ValueChanged<bool>? onAdult;
  final ValueChanged<bool> onTerms;
  final ValueChanged<bool> onPrivacy;

  @override
  Widget build(BuildContext context, WidgetRef ref) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      if (adult != null)
        CheckboxListTile(
          contentPadding: EdgeInsets.zero,
          controlAffinity: ListTileControlAffinity.leading,
          value: adult,
          onChanged: (v) => onAdult?.call(v ?? false),
          title: const Text('I am 18 or older'),
        ),
      CheckboxListTile(
        contentPadding: EdgeInsets.zero,
        controlAffinity: ListTileControlAffinity.leading,
        value: terms,
        onChanged: (v) => onTerms(v ?? false),
        title: const Text('I agree to the terms of service'),
        subtitle: const Text('Version $legalVersion'),
        secondary: IconButton(
          tooltip: 'Read the terms of service',
          icon: const Icon(Icons.open_in_new),
          onPressed: () => openLegalPage(ref, LegalPaths.terms),
        ),
      ),
      CheckboxListTile(
        contentPadding: EdgeInsets.zero,
        controlAffinity: ListTileControlAffinity.leading,
        value: privacy,
        onChanged: (v) => onPrivacy(v ?? false),
        title: const Text('I have read the privacy policy'),
        subtitle: const Text('Version $legalVersion'),
        secondary: IconButton(
          tooltip: 'Read the privacy policy',
          icon: const Icon(Icons.open_in_new),
          onPressed: () => openLegalPage(ref, LegalPaths.privacy),
        ),
      ),
    ],
  );
}
