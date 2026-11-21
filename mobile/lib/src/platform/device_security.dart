import 'dart:async';
import 'dart:io';

import 'package:barterly/src/crash/crash_reporter.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';

/// Screen protection and a rooted/jailbroken-device signal (docs/security.md).
///
/// - Android: FLAG_SECURE while a sensitive screen is open, so it can't be
///   screenshotted, recorded or shown in the app switcher.
/// - Both platforms: [SecureScreen] covers the content whenever the app is
///   inactive, which is when iOS takes its app-switcher snapshot.
/// - [integritySignals] looks for common root/jailbreak traces. It's a signal for
///   our error reports, not a block: these checks are easy to hide from, and
///   people with rooted phones are still allowed to use Barterly.
class DeviceSecurity {
  new({
    MethodChannel? channel,
    bool Function(String path)? exists,
    this._platform,
  }) : _channel = channel ?? const MethodChannel('in.barterly/device_security'),
       _exists = exists ?? ((path) => File(path).existsSync());

  /// The instance screens use; tests may replace it.
  static DeviceSecurity instance = DeviceSecurity();

  final MethodChannel _channel;
  final bool Function(String path) _exists;
  final TargetPlatform? _platform;
  int _secureScreens = 0;

  TargetPlatform get _os => _platform ?? defaultTargetPlatform;

  static const androidRootPaths = [
    '/system/bin/su',
    '/system/xbin/su',
    '/sbin/su',
    '/system/app/Superuser.apk',
    '/data/adb/magisk',
    '/system/bin/magisk',
  ];
  static const iosJailbreakPaths = [
    '/Applications/Cydia.app',
    '/Applications/Sileo.app',
    '/var/jb',
    '/private/var/lib/apt',
    '/usr/sbin/sshd',
    '/bin/bash',
  ];

  /// A sensitive screen opened ([on]) or closed. Nested screens are counted.
  Future<void> secureScreen({required bool on}) async {
    _secureScreens += on ? 1 : -1;
    if (_secureScreens < 0) _secureScreens = 0;
    if (_os != TargetPlatform.android) return;
    try {
      await _channel.invokeMethod<void>('setSecure', _secureScreens > 0);
    } on MissingPluginException {
      // Widget tests and platforms without the channel.
    } on PlatformException {
      // Never stop a screen opening over this.
    }
  }

  /// Traces of root or a jailbreak, e.g. ['su:/system/xbin/su', 'test-keys'].
  Future<List<String>> integritySignals() async {
    final signals = <String>[];
    switch (_os) {
      case TargetPlatform.android:
        for (final path in androidRootPaths) {
          if (_safeExists(path)) signals.add('su:$path');
        }
        try {
          final tags = await _channel.invokeMethod<String>('buildTags');
          if (tags != null && tags.contains('test-keys')) {
            signals.add('test-keys');
          }
        } on MissingPluginException {
          // ignore
        } on PlatformException {
          // ignore
        }
      case TargetPlatform.iOS:
        for (final path in iosJailbreakPaths) {
          if (_safeExists(path)) signals.add('jb:$path');
        }
      case TargetPlatform.fuchsia ||
          TargetPlatform.linux ||
          TargetPlatform.macOS ||
          TargetPlatform.windows:
        break;
    }
    return signals;
  }

  bool _safeExists(String path) {
    try {
      return _exists(path);
    } on Object {
      return false;
    }
  }
}

/// Sends one non-fatal report if the device shows root/jailbreak traces.
Future<void> reportDeviceIntegrity(
  DeviceSecurity security,
  CrashReporter crash,
) async {
  final signals = await security.integritySignals();
  if (signals.isEmpty) return;
  await crash.report(
    DeviceIntegrityNotice(signals),
    null,
    context: 'device_integrity',
  );
}

/// Reported (not thrown) when a device shows root/jailbreak traces.
class DeviceIntegrityNotice implements Exception {
  const new(this.signals);

  final List<String> signals;

  @override
  String toString() => 'Device integrity signals: ${signals.join(', ')}';
}

/// Wraps a screen showing money, credentials or emergency contacts.
class SecureScreen extends StatefulWidget {
  const new({required this.child, super.key});

  final Widget child;

  @override
  State<SecureScreen> createState() => _SecureScreenState();
}

class _SecureScreenState extends State<SecureScreen>
    with WidgetsBindingObserver {
  bool _covered = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    unawaited(DeviceSecurity.instance.secureScreen(on: true));
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    unawaited(DeviceSecurity.instance.secureScreen(on: false));
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final cover = state != AppLifecycleState.resumed;
    if (cover != _covered) setState(() => _covered = cover);
  }

  @override
  Widget build(BuildContext context) => Stack(
    children: [
      widget.child,
      if (_covered)
        Positioned.fill(
          child: ColoredBox(
            key: const Key('secure-screen-cover'),
            color: Theme.of(context).colorScheme.surface,
            child: const Center(child: Icon(Icons.lock_outline, size: 48)),
          ),
        ),
    ],
  );
}
