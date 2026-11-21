import 'package:geolocator/geolocator.dart';

/// Where the talent is, for the host's records at check-in. Never required: a
/// refusal or a slow fix just means no distance is recorded.
///
/// Permission is asked only when it's needed (opening the check-in pass), after
/// the app has explained why, and only for while the app is in use: check-in
/// never needs background location.
class Located {
  const new({
    required this.latitude,
    required this.longitude,
    required this.accuracyM,
  });

  final double latitude;
  final double longitude;
  final int accuracyM;

  Map<String, Object?> toJson() => {
    'latitude': latitude.toStringAsFixed(6),
    'longitude': longitude.toStringAsFixed(6),
    'accuracy_m': accuracyM,
  };
}

enum LocationAccess {
  /// Allowed while the app is in use.
  granted,

  /// Not asked yet: explain first, then ask.
  notAsked,

  /// Refused (asking again is pointless, or the system won't show the prompt).
  refused,

  /// Location is switched off on the phone.
  off,
}

abstract interface class LocationReader {
  Future<LocationAccess> access();

  /// Asks for permission (while in use). Call only after explaining why.
  Future<LocationAccess> request();

  /// The current position, if allowed and found in time; never asks.
  Future<Located?> current();
}

class GeolocatorReader implements LocationReader {
  static LocationAccess _of(LocationPermission p) => switch (p) {
    LocationPermission.always ||
    LocationPermission.whileInUse => LocationAccess.granted,
    LocationPermission.denied => LocationAccess.notAsked,
    LocationPermission.deniedForever ||
    LocationPermission.unableToDetermine => LocationAccess.refused,
  };

  @override
  Future<LocationAccess> access() async {
    try {
      if (!await Geolocator.isLocationServiceEnabled()) {
        return LocationAccess.off;
      }
      return _of(await Geolocator.checkPermission());
    } on Exception {
      return LocationAccess.refused;
    }
  }

  @override
  Future<LocationAccess> request() async {
    try {
      return _of(await Geolocator.requestPermission());
    } on Exception {
      return LocationAccess.refused;
    }
  }

  @override
  Future<Located?> current() async {
    try {
      if (await access() != LocationAccess.granted) return null;
      final position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: Duration(seconds: 10),
        ),
      );
      return Located(
        latitude: position.latitude,
        longitude: position.longitude,
        accuracyM: position.accuracy.round(),
      );
    } on Exception {
      return null;
    }
  }
}
