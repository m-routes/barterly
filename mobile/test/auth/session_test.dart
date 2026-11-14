import 'package:barterly/src/api/token_store.dart';
import 'package:barterly/src/auth/session.dart';
import 'package:barterly/src/auth/user.dart';
import 'package:barterly/src/profile/talent_profile.dart';
import 'package:barterly/src/providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers.dart';

ProviderContainer container(FakeApi api, TokenStore tokens) {
  final c = ProviderContainer(
    retry: (_, _) => null,
    overrides: testOverrides(api: api, tokens: tokens),
  );
  addTearDown(c.dispose);
  return c;
}

/// Waits until the session leaves [SessionLoading].
Future<SessionState> settled(ProviderContainer c) async {
  c.read(sessionProvider);
  for (var i = 0; i < 50; i++) {
    await Future<void>.delayed(Duration.zero);
    final state = c.read(sessionProvider);
    if (state is! SessionLoading) return state;
  }
  fail('session never settled');
}

void main() {
  group('session', () {
    test('no stored tokens: signed out, without calling the API', () async {
      final api = FakeApi();
      final state = await settled(container(api, MemoryTokenStore()));
      expect(state, isA<SignedOut>());
      expect(api.requests, isEmpty);
    });

    test('stored tokens: loads the user from /me', () async {
      final api = FakeApi({'GET /api/v1/me/': (_) => ok(talentJson)});
      final state = await settled(
        container(api, MemoryTokenStore(signedInTokens)),
      );
      expect(state, isA<SignedIn>());
      expect((state as SignedIn).user.role, UserRole.talent);
    });

    test('API down at launch: a retryable failure, tokens kept', () async {
      final tokens = MemoryTokenStore(signedInTokens);
      final api = FakeApi({
        'GET /api/v1/me/': (_) => apiError(502, 'api_unavailable'),
      });
      final c = container(api, tokens);
      expect(await settled(c), isA<SessionFailed>());
      expect(await tokens.read(), isNotNull);

      api.routes['GET /api/v1/me/'] = (_) => ok(talentJson);
      await c.read(sessionProvider.notifier).reload();
      expect(c.read(sessionProvider), isA<SignedIn>());
    });

    test('rejected tokens at launch: signed out and forgotten', () async {
      final tokens = MemoryTokenStore(signedInTokens);
      final api = FakeApi({
        'GET /api/v1/me/': (_) => apiError(401, 'token_not_valid'),
        'POST /api/v1/auth/refresh/': (_) => apiError(401, 'token_not_valid'),
      });
      expect(await settled(container(api, tokens)), isA<SignedOut>());
      expect(await tokens.read(), isNull);
    });

    test('sign out tells the API and forgets the tokens', () async {
      final tokens = MemoryTokenStore(signedInTokens);
      final api = FakeApi({
        'GET /api/v1/me/': (_) => ok(talentJson),
        'POST /api/v1/auth/logout/': (r) {
          expect(r.data, {'refresh': 'refresh-1'});
          return const FakeResponse(204);
        },
      });
      final c = container(api, tokens);
      await settled(c);
      await c.read(sessionProvider.notifier).signOut();
      expect(c.read(sessionProvider), isA<SignedOut>());
      expect(await tokens.read(), isNull);
    });

    test('sign out still works offline', () async {
      final tokens = MemoryTokenStore(signedInTokens);
      final api = FakeApi({
        'GET /api/v1/me/': (_) => ok(talentJson),
        'POST /api/v1/auth/logout/': (_) => apiError(503, 'down'),
      });
      final c = container(api, tokens);
      await settled(c);
      await c.read(sessionProvider.notifier).signOut();
      expect(await tokens.read(), isNull);
    });
  });

  group('repositories', () {
    test('exchange stores the API tokens and returns the user', () async {
      final tokens = MemoryTokenStore();
      final api = FakeApi({
        'POST /api/v1/auth/exchange/': (r) {
          expect(r.data, {'id_token': 'firebase-id-token'});
          return ok({
            'access': 'a',
            'refresh': 'r',
            'is_new_user': true,
            'needs_role': true,
            'profile_complete': false,
            'user': userJson(role: '', complete: false),
          });
        },
      });
      final user = await container(
        api,
        tokens,
      ).read(authRepositoryProvider).exchange('firebase-id-token');
      expect(user.role, UserRole.none);
      expect((await tokens.read())?.refresh, 'r');
    });

    test('a missing talent profile is null, not an error', () async {
      final api = FakeApi({
        'GET /api/v1/profiles/talent/me/': (_) =>
            apiError(404, 'profile_not_found'),
      });
      final repo = container(
        api,
        MemoryTokenStore(signedInTokens),
      ).read(profileRepositoryProvider);
      expect(await repo.fetchTalentProfile(), isNull);
    });

    test('saving sends the API field names and a plain date', () async {
      Object? sent;
      final api = FakeApi({
        'PATCH /api/v1/profiles/talent/me/': (r) {
          sent = r.data;
          return ok({...?(r.data as Map<String, Object?>?), 'id': 'p1'});
        },
      });
      final repo = container(
        api,
        MemoryTokenStore(signedInTokens),
      ).read(profileRepositoryProvider);
      await repo.saveTalentProfile(
        TalentProfile(
          displayName: 'Asha',
          talentType: TalentType.artist,
          skills: const ['mural-painting'],
          languages: const ['en', 'hi'],
          dateOfBirth: DateTime(2001, 3, 9),
          emergencyContactPhone: '+919811111111',
        ),
      );
      expect(sent, containsPair('talent_type', 'artist'));
      expect(sent, containsPair('date_of_birth', '2001-03-09'));
      expect(sent, containsPair('skills', ['mural-painting']));
      expect(sent, containsPair('emergency_contact_phone', '+919811111111'));
    });
  });
}
