import 'dart:async';

import 'package:barterly/src/providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Opens a public legal page (terms, privacy policy, grievance officer) from
/// the web site in the in-app browser.
void openLegalPage(WidgetRef ref, String path) {
  final base = ref.read(appConfigProvider).webBaseUrl;
  unawaited(ref.read(urlOpenerProvider).openInApp(Uri.parse('$base$path')));
}
