import 'package:geolocator/geolocator.dart';

/// Where the talent is, for the host's records at check-in. Never required: a
/// refusal or a slow fix just means no distance is recorded.
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

abstract interface class LocationReader {
  Future<Located?> current();
}

class GeolocatorReader implements LocationReader {
  @override
  Future<Located?> current() async {
    try {
      if (!await Geolocator.isLocationServiceEnabled()) return null;
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        return null;
      }
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
