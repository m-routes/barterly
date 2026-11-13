import 'dart:async';

import 'package:firebase_auth/firebase_auth.dart';

/// Proves a phone number with an SMS code. Firebase is only used for that: its
/// ID token is exchanged once for the API's own tokens, then dropped.
abstract interface class PhoneAuth {
  /// Starts verification for an E.164 number.
  Future<PhoneVerification> sendCode(String phoneE164);

  /// Ends the Firebase session after the exchange.
  Future<void> signOut();
}

sealed class PhoneVerification {
  const new();
}

/// An SMS was sent; [confirm] checks the code and returns the ID token.
final class CodeSent extends PhoneVerification {
  const new(this.confirm);
  final Future<String> Function(String code) confirm;
}

/// Android read the SMS itself; no code to type.
final class AutoVerified extends PhoneVerification {
  const new(this.idToken);
  final String idToken;
}

/// A failure the person can understand and act on.
class PhoneAuthException implements Exception {
  const new(this.code, this.message);

  factory fromCode(String code) =>
      PhoneAuthException(code, _messages[code] ?? _fallback);

  final String code;
  final String message;

  static const _fallback = "We couldn't sign you in. Try again.";
  static const _messages = {
    'invalid-phone-number':
        "That number doesn't look right. Check it and try again.",
    'too-many-requests': 'Too many attempts. Wait a few minutes and try again.',
    'quota-exceeded': "We can't send codes right now. Try again later.",
    'invalid-verification-code':
        "That code isn't right. Check the SMS and try again.",
    'session-expired': 'That code has expired. Send a new one.',
    'network-request-failed':
        'You seem to be offline. Check your connection and try again.',
    'user-disabled': 'This number has been blocked from signing in.',
    'app-not-authorized':
        "This version of the app can't sign in. Update it and try again.",
  };

  @override
  String toString() => 'PhoneAuthException($code)';
}

/// The real implementation over firebase_auth.
class FirebasePhoneAuth implements PhoneAuth {
  new([FirebaseAuth? auth]) : _auth = auth ?? FirebaseAuth.instance;

  final FirebaseAuth _auth;
  int? _resendToken;

  Future<String> _signIn(PhoneAuthCredential credential) async {
    try {
      final result = await _auth.signInWithCredential(credential);
      final token = await result.user?.getIdToken();
      if (token == null) throw PhoneAuthException.fromCode('unknown');
      return token;
    } on FirebaseAuthException catch (error) {
      throw PhoneAuthException.fromCode(error.code);
    }
  }

  @override
  Future<PhoneVerification> sendCode(String phoneE164) {
    final result = Completer<PhoneVerification>();
    unawaited(
      _auth
          .verifyPhoneNumber(
            phoneNumber: phoneE164,
            forceResendingToken: _resendToken,
            timeout: const Duration(seconds: 60),
            verificationCompleted: (credential) async {
              if (result.isCompleted) return;
              try {
                result.complete(AutoVerified(await _signIn(credential)));
              } on PhoneAuthException catch (error) {
                result.completeError(error);
              }
            },
            verificationFailed: (error) {
              if (!result.isCompleted) {
                result.completeError(PhoneAuthException.fromCode(error.code));
              }
            },
            codeSent: (verificationId, resendToken) {
              _resendToken = resendToken;
              if (result.isCompleted) return;
              result.complete(
                CodeSent(
                  (code) => _signIn(
                    PhoneAuthProvider.credential(
                      verificationId: verificationId,
                      smsCode: code,
                    ),
                  ),
                ),
              );
            },
            codeAutoRetrievalTimeout: (_) {},
          )
          .catchError((Object error) {
            if (!result.isCompleted) {
              result.completeError(
                error is FirebaseAuthException
                    ? PhoneAuthException.fromCode(error.code)
                    : PhoneAuthException.fromCode('unknown'),
              );
            }
          }),
    );
    return result.future;
  }

  @override
  Future<void> signOut() => _auth.signOut();
}

/// Used when this build has no Firebase config: every attempt explains that.
class UnavailablePhoneAuth implements PhoneAuth {
  const new();

  @override
  Future<PhoneVerification> sendCode(String phoneE164) async =>
      throw const PhoneAuthException(
        'not-configured',
        "Sign-in isn't available in this build yet.",
      );

  @override
  Future<void> signOut() async {}
}
