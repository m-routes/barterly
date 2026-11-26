import 'dart:io';

import 'package:barterly/src/platform/key_value_store.dart';
import 'package:barterly/src/platform/permission_rationale.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  late MemoryKeyValueStore store;
  late List<AppPermission> shown;
  late bool answer;
  late DateTime now;

  PermissionPrompts prompts() => PermissionPrompts(
    store: store,
    present: (p) async {
      shown.add(p);
      return answer;
    },
    now: () => now,
  );

  setUp(() {
    store = MemoryKeyValueStore();
    shown = [];
    answer = true;
    now = DateTime.utc(2026, 11, 24);
  });

  test('camera: explained the first time only', () async {
    expect(await prompts().explain(AppPermission.camera), isTrue);
    expect(await prompts().explain(AppPermission.camera), isTrue);
    expect(shown, [AppPermission.camera]);
  });

  test('camera: "Not now" asks again on the next tap', () async {
    answer = false;
    expect(await prompts().explain(AppPermission.camera), isFalse);
    answer = true;
    expect(await prompts().explain(AppPermission.camera), isTrue);
    expect(shown, [AppPermission.camera, AppPermission.camera]);
  });

  test('notifications: "Not now" is respected for 30 days', () async {
    answer = false;
    expect(await prompts().explain(AppPermission.notifications), isFalse);
    now = now.add(const Duration(days: 29));
    expect(await prompts().explain(AppPermission.notifications), isFalse);
    expect(shown, hasLength(1));
    now = now.add(const Duration(days: 2));
    answer = true;
    expect(await prompts().explain(AppPermission.notifications), isTrue);
    expect(shown, hasLength(2));
  });

  test('every permission has a rationale', () {
    expect(rationales.keys.toSet(), AppPermission.values.toSet());
  });

  test("iOS has a purpose string for every permission the app's SDKs ask", () {
    final plist = File('ios/Runner/Info.plist').readAsStringSync();
    for (final key in [
      'NSCameraUsageDescription',
      'NSMicrophoneUsageDescription',
      'NSPhotoLibraryUsageDescription',
      'NSLocationWhenInUseUsageDescription',
    ]) {
      final match = RegExp('<key>$key</key>\\s*<string>([^<]{20,})</string>')
          .firstMatch(plist);
      expect(match, isNotNull, reason: key);
    }
  });

  test('Android declares the notification permission (Android 13+)', () {
    final manifest = File('android/app/src/main/AndroidManifest.xml')
        .readAsStringSync();
    expect(manifest, contains('android.permission.POST_NOTIFICATIONS'));
  });
}
