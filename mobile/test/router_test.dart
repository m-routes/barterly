import 'package:barterly/src/auth/session.dart';
import 'package:barterly/src/auth/user.dart';
import 'package:barterly/src/router.dart';
import 'package:flutter_test/flutter_test.dart';

SignedIn signedIn(UserRole role, {bool complete = true}) => SignedIn(
  User(id: 'u1', phone: '+919876543210', role: role, profileComplete: complete),
);

void main() {
  test('loading and failed sessions wait on the splash screen', () {
    expect(redirectFor(const SessionLoading(), '/discover'), '/splash');
    expect(redirectFor(const SessionLoading(), '/splash'), isNull);
  });

  test('signed-out people go to login from anywhere', () {
    expect(redirectFor(const SignedOut(), '/wallet'), '/login');
    expect(redirectFor(const SignedOut(), '/login'), isNull);
  });

  test('a new account picks talent first', () {
    expect(redirectFor(signedIn(UserRole.none), '/login'), '/join');
  });

  test('vendors and admins are told this app is for talent', () {
    expect(redirectFor(signedIn(UserRole.vendor), '/discover'), '/wrong-app');
    expect(redirectFor(signedIn(UserRole.admin), '/login'), '/wrong-app');
  });

  test('talent finish their profile before anything else', () {
    final talent = signedIn(UserRole.talent, complete: false);
    expect(redirectFor(talent, '/discover'), '/setup');
    expect(redirectFor(talent, '/setup'), isNull);
  });

  test('complete talent leave the gates for Discover, and stay elsewhere', () {
    final talent = signedIn(UserRole.talent);
    for (final gate in ['/splash', '/login', '/join', '/setup', '/wrong-app']) {
      expect(redirectFor(talent, gate), '/discover', reason: gate);
    }
    expect(redirectFor(talent, '/wallet'), isNull);
    expect(redirectFor(talent, '/profile/edit'), isNull);
  });
}
