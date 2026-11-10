import 'package:barterly/src/app.dart';
import 'package:barterly/src/pay_model.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('home screen lists every pay model', (tester) async {
    await tester.pumpWidget(const BarterlyApp());

    expect(find.text('Barterly'), findsOneWidget);
    for (final model in PayModel.values) {
      expect(find.byKey(ValueKey('pay-model-${model.name}')), findsOneWidget);
    }
  });
}
