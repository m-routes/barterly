import 'package:barterly/src/crash/crash_reporter.dart';
import 'package:barterly/src/platform/device_security.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

class _Crash implements CrashReporter {
  final reports = <(Object, String?)>[];

  @override
  Future<void> report(
    Object error,
    StackTrace? stack, {
    String? context,
  }) async => reports.add((error, context));

  @override
  Future<void> setUser(String? userId) async {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('test/device_security');
  final calls = <MethodCall>[];
  var buildTags = 'release-keys';

  setUp(() {
    calls.clear();
    buildTags = 'release-keys';
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          calls.add(call);
          return call.method == 'buildTags' ? buildTags : null;
        });
  });

  DeviceSecurity android({Set<String> files = const {}}) => DeviceSecurity(
    channel: channel,
    exists: files.contains,
    platform: TargetPlatform.android,
  );

  group('integritySignals', () {
    test('a clean Android device has none', () async {
      expect(await android().integritySignals(), isEmpty);
    });

    test('su binaries and test-keys builds are reported', () async {
      buildTags = 'test-keys';
      final signals = await android(files: {'/system/xbin/su'})
          .integritySignals();
      expect(signals, ['su:/system/xbin/su', 'test-keys']);
    });

    test('jailbreak traces on iOS', () async {
      final ios = DeviceSecurity(
        channel: channel,
        exists: {'/Applications/Cydia.app'}.contains,
        platform: TargetPlatform.iOS,
      );
      expect(await ios.integritySignals(), ['jb:/Applications/Cydia.app']);
    });

    test('a check that throws counts as absent', () async {
      final security = DeviceSecurity(
        channel: channel,
        exists: (_) => throw const FileSystemExceptionLike(),
        platform: TargetPlatform.iOS,
      );
      expect(await security.integritySignals(), isEmpty);
    });
  });

  test(
    'signals are reported once as a non-fatal notice, never thrown',
    () async {
      final crash = _Crash();
      await reportDeviceIntegrity(android(), crash);
      expect(crash.reports, isEmpty);

      await reportDeviceIntegrity(android(files: {'/sbin/su'}), crash);
      expect(crash.reports, hasLength(1));
      expect(crash.reports.single.$1, isA<DeviceIntegrityNotice>());
      expect(crash.reports.single.$2, 'device_integrity');
    },
  );

  test('FLAG_SECURE stays on until the last secure screen closes', () async {
    final security = android();
    await security.secureScreen(on: true);
    await security.secureScreen(on: true);
    await security.secureScreen(on: false);
    await security.secureScreen(on: false);
    expect(calls.map((c) => c.arguments), [true, true, true, false]);
  });

  testWidgets('a secure screen sets the flag and covers itself when inactive', (
    tester,
  ) async {
    final previous = DeviceSecurity.instance;
    addTearDown(() => DeviceSecurity.instance = previous);
    DeviceSecurity.instance = android();

    await tester.pumpWidget(
      const MaterialApp(home: SecureScreen(child: Text('IFSC HDFC0001234'))),
    );
    expect(calls.last.arguments, isTrue);
    expect(find.byKey(const Key('secure-screen-cover')), findsNothing);

    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    await tester.pump();
    expect(find.byKey(const Key('secure-screen-cover')), findsOneWidget);

    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump();
    expect(find.byKey(const Key('secure-screen-cover')), findsNothing);

    await tester.pumpWidget(const MaterialApp(home: Text('elsewhere')));
    expect(calls.last.arguments, isFalse);
  });
}

class FileSystemExceptionLike implements Exception {
  const new();
}
