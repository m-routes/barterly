import 'dart:async';

import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/auth/user.dart';
import 'package:barterly/src/platform/device_keys.dart';
import 'package:barterly/src/providers.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Who is using the app right now.
sealed class SessionState {
  const new();
}

/// Checking stored tokens against the API at launch.
final class SessionLoading extends SessionState {
  const new();
}

final class SignedOut extends SessionState {
  const new();
}

@immutable
final class SignedIn extends SessionState {
  const new(this.user);
  final User user;

  @override
  bool operator ==(Object other) => other is SignedIn && other.user == user;

  @override
  int get hashCode => user.hashCode;
}

/// Tokens exist but /me failed for another reason (offline, API down).
final class SessionFailed extends SessionState {
  const new(this.error);
  final ApiError error;
}

final sessionProvider = NotifierProvider<SessionController, SessionState>(
  SessionController.new,
);

class SessionController extends Notifier<SessionState> {
  @override
  SessionState build() {
    unawaited(Future.microtask(restore));
    return const SessionLoading();
  }

  /// Load the user for stored tokens, if there are any.
  Future<void> restore() async {
    final auth = ref.read(authRepositoryProvider);
    if (!await auth.hasSession) {
      state = const SignedOut();
      return;
    }
    state = const SessionLoading();
    await reload();
  }

  /// Fetch /me again (after choosing a role or saving the profile).
  Future<void> reload() async {
    try {
      state = SignedIn(await ref.read(authRepositoryProvider).me());
    } on ApiError catch (error) {
      // A 401 here means the refresh failed too; the interceptor already
      // cleared the tokens and called [expired].
      state = error.isUnauthorized ? const SignedOut() : SessionFailed(error);
    }
  }

  void signedIn(User user) => state = SignedIn(user);

  /// The refresh token was rejected: the person has to sign in again.
  void expired() {
    if (state is! SignedOut) state = const SignedOut();
  }

  Future<void> signOut() async {
    final current = state;
    await ref.read(authRepositoryProvider).signOut();
    if (current is SignedIn) await _forget(current.user.id);
    state = const SignedOut();
  }

  /// Drops what the device kept for this account (offline feed, unsent
  /// applications), so the next person on this phone can't see it.
  Future<void> _forget(String userId) async {
    final store = ref.read(keyValueStoreProvider);
    for (final key in DeviceKeys.forUser(userId)) {
      try {
        await store.remove(key);
      } on Object {
        // Storage unavailable: nothing more to do.
      }
    }
  }
}
