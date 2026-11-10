import 'package:barterly/main.dart' as app;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('app launches to the home screen', (tester) async {
    app.main();
    await tester.pumpAndSettle();

    expect(find.byType(ListTile), findsNWidgets(4));
  });
}
