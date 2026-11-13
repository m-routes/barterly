import 'dart:async';

import 'package:barterly/src/auth/session.dart';
import 'package:barterly/src/providers.dart';
import 'package:barterly/src/router.dart';
import 'package:barterly/src/theme/app_theme.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

class BarterlyApp extends ConsumerWidget {
  const new({this.brandFonts = true, super.key});

  /// Tests turn this off so no fonts are fetched.
  final bool brandFonts;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Tag crash reports with the account id (not the phone number).
    ref.listen(sessionProvider, (_, next) {
      unawaited(
        ref
            .read(crashReporterProvider)
            .setUser(next is SignedIn ? next.user.id : null),
      );
    });
    return MaterialApp.router(
      title: 'Barterly',
      debugShowCheckedModeBanner: false,
      theme: barterlyTheme(brandFonts: brandFonts),
      routerConfig: ref.watch(routerProvider),
    );
  }
}
