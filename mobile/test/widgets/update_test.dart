import 'package:barterly/src/api/token_store.dart';
import 'package:barterly/src/platform/key_value_store.dart';
import 'package:barterly/src/update/update_gate.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers.dart';

Map<String, Object?> versions({
  required String minimum,
  required String latest,
  String message = '',
}) => {
  ...upToDate,
  'minimum_version': minimum,
  'latest_version': latest,
  'message': message,
};

void main() {
  testWidgets('a version below the minimum is blocked on launch', (
    tester,
  ) async {
    usePhoneScreen(tester);
    final urls = FakeUrlOpener();
    final api = FakeApi({
      'GET /api/v1/app/version/': (r) {
        expect(r.queryParameters, {'platform': 'android', 'version': '1.0.0'});
        return ok(
          versions(minimum: '1.1.0', latest: '1.1.0', message: 'New payouts.'),
        );
      },
    });
    await pumpApp(tester, api: api, urls: urls);

    expect(find.text('Update Barterly to continue'), findsOneWidget);
    expect(find.text('New payouts.'), findsOneWidget);
    await tester.tap(find.text('Update now'));
    expect(urls.external.single.host, 'play.google.com');
  });

  testWidgets('any call answered 426 blocks the app', (tester) async {
    usePhoneScreen(tester);
    final api = talentApi({
      'GET /api/v1/me/': (_) => apiError(
        426,
        'upgrade_required',
        'This version of Barterly is no longer supported.',
        {'minimum_version': '2.0.0', 'store_url': 'https://store.test/a'},
      ),
    });
    await pumpApp(tester, api: api, tokens: MemoryTokenStore(signedInTokens));

    expect(find.text('Update Barterly to continue'), findsOneWidget);
    expect(find.byType(ForceUpdateScreen), findsOneWidget);
  });

  testWidgets('a newer version is offered once, and "Later" is remembered', (
    tester,
  ) async {
    usePhoneScreen(tester);
    final store = MemoryKeyValueStore();
    final api = FakeApi({
      'GET /api/v1/app/version/': (_) =>
          ok(versions(minimum: '0.9.0', latest: '1.2.0')),
    });
    await pumpApp(tester, api: api, store: store);

    expect(
      find.text('A new version of Barterly is available.'),
      findsOneWidget,
    );
    await tester.tap(find.text('Later'));
    await tester.pumpAndSettle();
    expect(find.text('A new version of Barterly is available.'), findsNothing);
    expect(store.data[UpdateController.dismissedKey], {'version': '1.2.0'});

    // Next launch: same latest version, so nothing is shown.
    await pumpApp(tester, api: api, store: store);
    expect(find.text('A new version of Barterly is available.'), findsNothing);
  });

  testWidgets('offline at launch: the app carries on', (tester) async {
    usePhoneScreen(tester);
    final api = FakeApi()..offline = true;
    await pumpApp(tester, api: api);
    expect(find.byType(ForceUpdateScreen), findsNothing);
  });
}
