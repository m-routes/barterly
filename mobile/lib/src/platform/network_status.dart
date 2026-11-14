import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';

/// Whether the device has a network interface up.
///
/// This can't promise the API is reachable (captive portals, dead Wi-Fi), so
/// screens also treat a `network_error` from the API as offline.
abstract interface class NetworkStatus {
  Future<bool> isOnline();

  /// Emits when connectivity changes (true = some network is up).
  Stream<bool> get changes;
}

class ConnectivityNetworkStatus implements NetworkStatus {
  new([Connectivity? connectivity])
    : _connectivity = connectivity ?? Connectivity();

  final Connectivity _connectivity;

  static bool _up(List<ConnectivityResult> results) =>
      results.any((r) => r != ConnectivityResult.none);

  @override
  Future<bool> isOnline() async {
    try {
      return _up(await _connectivity.checkConnectivity());
    } on Object {
      // If the plugin can't tell, assume online and let requests decide.
      return true;
    }
  }

  @override
  Stream<bool> get changes =>
      _connectivity.onConnectivityChanged.map(_up).distinct();
}

/// A switch tests flip by hand.
class FakeNetworkStatus implements NetworkStatus {
  new({this._online = true});

  bool _online;
  final _controller = StreamController<bool>.broadcast();

  bool get online => _online;

  set online(bool value) {
    if (value == _online) return;
    _online = value;
    _controller.add(value);
  }

  @override
  Future<bool> isOnline() async => _online;

  @override
  Stream<bool> get changes => _controller.stream;
}
