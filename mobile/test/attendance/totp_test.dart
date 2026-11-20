import 'dart:convert';

import 'package:barterly/src/attendance/totp.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('matches the RFC 6238 SHA-1 vector at a 5-minute step', () {
    const secret = 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ';
    final counterOne = DateTime.fromMillisecondsSinceEpoch(300000, isUtc: true);
    expect(codeAt(secret, counterOne), '287082');
  });

  test("matches the server's code for the same secret and time", () {
    // From apps/attendance/signing.py (and web crypto.test.ts).
    expect(codeAt('JBSWY3DPEHPK3PXP', DateTime.utc(2026, 12, 1, 10)), '832515');
  });

  test('counts down to the next code', () {
    final at = DateTime.fromMillisecondsSinceEpoch(310000, isUtc: true);
    expect(codeTimeLeft(at), const Duration(seconds: 290));
  });

  test('decodes base32', () {
    expect(utf8.decode(base32Decode('JBSWY3DP')), 'Hello');
    expect(() => base32Decode('1'), throwsFormatException);
  });
}
