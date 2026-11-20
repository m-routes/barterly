import 'dart:typed_data';

import 'package:crypto/crypto.dart';

/// The six-digit fallback code (RFC 6238: HMAC-SHA1, a [periodSeconds] step),
/// the same as the server and the host's console compute. Works offline.
String codeAt(String base32Secret, DateTime at, {int periodSeconds = 300}) {
  final counter = at.millisecondsSinceEpoch ~/ 1000 ~/ periodSeconds;
  final message = ByteData(8)..setInt64(0, counter);
  final digest = Hmac(
    sha1,
    base32Decode(base32Secret),
  ).convert(message.buffer.asUint8List()).bytes;
  final offset = digest.last & 0x0f;
  final number =
      ((digest[offset] & 0x7f) << 24) |
      (digest[offset + 1] << 16) |
      (digest[offset + 2] << 8) |
      digest[offset + 3];
  return (number % 1000000).toString().padLeft(6, '0');
}

/// How long the current code has left.
Duration codeTimeLeft(DateTime at, {int periodSeconds = 300}) {
  final seconds = at.millisecondsSinceEpoch ~/ 1000;
  return Duration(seconds: periodSeconds - seconds % periodSeconds);
}

const _alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';

List<int> base32Decode(String input) {
  final out = <int>[];
  var buffer = 0;
  var bits = 0;
  for (final ch in input.toUpperCase().replaceAll('=', '').split('')) {
    final index = _alphabet.indexOf(ch);
    if (index < 0) throw FormatException('Not base32: $ch');
    buffer = (buffer << 5) | index;
    bits += 5;
    if (bits >= 8) {
      out.add((buffer >> (bits - 8)) & 0xff);
      bits -= 8;
    }
  }
  return out;
}
