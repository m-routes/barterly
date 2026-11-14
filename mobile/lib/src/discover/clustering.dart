import 'dart:math' as math;

import 'package:flutter/foundation.dart';

/// A group of nearby items drawn as one marker.
@immutable
class Cluster<T> {
  const new({
    required this.latitude,
    required this.longitude,
    required this.items,
  });

  final double latitude;
  final double longitude;
  final List<T> items;

  bool get isSingle => items.length == 1;
}

/// Web Mercator pixel position of a point at [zoom] (256-pixel tiles).
math.Point<double> projectToPixels(double lat, double lng, double zoom) {
  final scale = 256 * math.pow(2, zoom).toDouble();
  final clamped = lat.clamp(-85.05112878, 85.05112878);
  final sin = math.sin(clamped * math.pi / 180);
  final x = (lng + 180) / 360 * scale;
  final y = (0.5 - math.log((1 + sin) / (1 - sin)) / (4 * math.pi)) * scale;
  return math.Point(x, y);
}

/// Groups items whose points fall in the same [cellPx]-pixel grid square at
/// [zoom]. Grid clustering is simple and stable (the same items cluster the
/// same way for a given zoom), which is all a few hundred gigs need.
///
/// Each cluster sits at the average of its items' points. Items without a
/// point ([pointOf] returns null) are left out: the API sends no location
/// for some properties.
List<Cluster<T>> clusterByGrid<T>(
  Iterable<T> items, {
  required ({double latitude, double longitude})? Function(T item) pointOf,
  required double zoom,
  double cellPx = 64,
}) {
  final cells = <(int, int), List<(T, double, double)>>{};
  for (final item in items) {
    final point = pointOf(item);
    if (point == null) continue;
    final px = projectToPixels(point.latitude, point.longitude, zoom);
    final key = ((px.x / cellPx).floor(), (px.y / cellPx).floor());
    (cells[key] ??= []).add((item, point.latitude, point.longitude));
  }
  return [
    for (final members in cells.values)
      Cluster<T>(
        latitude:
            members.map((m) => m.$2).reduce((a, b) => a + b) / members.length,
        longitude:
            members.map((m) => m.$3).reduce((a, b) => a + b) / members.length,
        items: [for (final m in members) m.$1],
      ),
  ];
}
