import 'package:barterly/src/config/env.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('only local debug builds skip Firebase app verification', () {
    expect(skipAppVerification(AppEnv.local, debug: true), isTrue);
    expect(skipAppVerification(AppEnv.local, debug: false), isFalse);
    expect(skipAppVerification(AppEnv.staging, debug: true), isFalse);
    expect(skipAppVerification(AppEnv.production, debug: true), isFalse);
  });
}
