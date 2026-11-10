import 'package:barterly/src/pay_model.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('PayModel has the four supported models in order', () {
    expect(PayModel.values.map((m) => m.name), [
      'volunteer',
      'barter',
      'hybrid',
      'paid',
    ]);
  });

  test('description combines label and summary', () {
    expect(PayModel.hybrid.description, 'Hybrid: Stay plus stipend');
  });
}
