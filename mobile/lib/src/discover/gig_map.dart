import 'dart:async';

import 'package:barterly/src/discover/clustering.dart';
import 'package:barterly/src/discover/discovery_filters.dart';
import 'package:barterly/src/discover/gig.dart';
import 'package:barterly/src/providers.dart';
import 'package:barterly/src/theme/tokens.dart';
import 'package:barterly/src/widgets/feedback.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:latlong2/latlong.dart';
import 'package:material_ui/material_ui.dart';

/// Identifies the app to the tile server, as OpenStreetMap's tile policy asks.
const mapUserAgentPackage = 'in.barterly.barterly';
final Uri osmCopyright = Uri.parse('https://www.openstreetmap.org/copyright');

/// Roughly the middle of India, for when no gig has a location.
const _indiaCenter = LatLng(22.5, 79);

({double latitude, double longitude})? _pointOf(Gig gig) {
  final loc = gig.property.location;
  return loc == null
      ? null
      : (latitude: loc.latitude, longitude: loc.longitude);
}

/// Discover on a map. Each gig shows at its property's approximate point (the
/// API never sends the exact one before a booking) with the radius it could
/// be in; nearby gigs cluster.
class GigMap extends ConsumerStatefulWidget {
  const new({
    required this.gigs,
    required this.onOpen,
    required this.onSearchArea,
    super.key,
  });

  final List<Gig> gigs;
  final void Function(Gig gig) onOpen;

  /// The talent asked for gigs in the visible area: its centre and a radius
  /// covering it (the API's latitude, longitude and radius_km).
  final void Function(SearchPoint point, double radiusKm) onSearchArea;

  @override
  ConsumerState<GigMap> createState() => _GigMapState();
}

class _GigMapState extends ConsumerState<GigMap> {
  final _controller = MapController();
  double _zoom = 5;
  Gig? _selected;
  bool _moved = false;

  void _searchHere() {
    final camera = _controller.camera;
    final bounds = camera.visibleBounds;
    final halfDiagonal =
        const Distance().as(
          LengthUnit.Kilometer,
          bounds.northWest,
          bounds.southEast,
        ) /
        2;
    widget.onSearchArea(
      SearchPoint(
        latitude: camera.center.latitude,
        longitude: camera.center.longitude,
        label: 'Map area',
      ),
      halfDiagonal.clamp(1, 1000).toDouble(),
    );
    setState(() => _moved = false);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  List<LatLng> get _points => [
    for (final g in widget.gigs)
      if (_pointOf(g) case final p?) LatLng(p.latitude, p.longitude),
  ];

  @override
  Widget build(BuildContext context) {
    final config = ref.watch(appConfigProvider);
    final tiles = ref.watch(mapTileProviderProvider);
    final points = _points;
    final clusters = clusterByGrid(widget.gigs, pointOf: _pointOf, zoom: _zoom);
    final missing = widget.gigs.length - points.length;
    return Stack(
      children: [
        FlutterMap(
          mapController: _controller,
          options: MapOptions(
            initialCenter: _indiaCenter,
            initialZoom: _zoom,
            initialCameraFit: points.isEmpty
                ? null
                : CameraFit.coordinates(
                    coordinates: points,
                    maxZoom: points.length == 1 ? 11 : 13,
                    padding: const EdgeInsets.all(48),
                  ),
            minZoom: 3,
            maxZoom: 15,
            onPositionChanged: (camera, hasGesture) {
              // Re-cluster only when the zoom changes by a step.
              final rezoom = (camera.zoom - _zoom).abs() >= 0.5;
              if (rezoom || (hasGesture && !_moved)) {
                setState(() {
                  _zoom = camera.zoom;
                  _moved = _moved || hasGesture;
                });
              }
            },
            onTap: (_, _) => setState(() => _selected = null),
          ),
          children: [
            TileLayer(
              urlTemplate: config.mapTileUrl,
              userAgentPackageName: mapUserAgentPackage,
              tileProvider: tiles,
              // OSM asks apps not to prefetch or bulk download.
              keepBuffer: 1,
              panBuffer: 0,
            ),
            if (_zoom >= 10)
              CircleLayer(
                circles: [
                  for (final c in clusters)
                    if (c.isSingle)
                      if (c.items.single.property.location case final loc?)
                        CircleMarker(
                          point: LatLng(loc.latitude, loc.longitude),
                          radius: loc.radiusM,
                          useRadiusInMeter: true,
                          color: BarterlyColors.accent.withValues(alpha: 0.12),
                          borderColor: BarterlyColors.accent.withValues(
                            alpha: 0.5,
                          ),
                          borderStrokeWidth: 1,
                        ),
                ],
              ),
            MarkerLayer(
              markers: [
                for (final c in clusters)
                  Marker(
                    point: LatLng(c.latitude, c.longitude),
                    width: c.isSingle ? 48 : 52,
                    height: c.isSingle ? 48 : 52,
                    child: c.isSingle
                        ? _GigPin(
                            gig: c.items.single,
                            selected: _selected?.id == c.items.single.id,
                            onTap: () =>
                                setState(() => _selected = c.items.single),
                          )
                        : _ClusterBubble(
                            count: c.items.length,
                            onTap: () => _controller.move(
                              LatLng(c.latitude, c.longitude),
                              (_zoom + 2).clamp(3, 15),
                            ),
                          ),
                  ),
              ],
            ),
          ],
        ),
        Positioned(
          left: 12,
          right: 12,
          top: 12,
          child: Semantics(
            liveRegion: true,
            child: SurfaceCard(
              radius: 14,
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              child: Text(
                [
                  'Pins show the area, not the exact address.',
                  if (missing == 1) '1 gig has no location.',
                  if (missing > 1) '$missing gigs have no location.',
                ].join(' '),
                style: const TextStyle(
                  fontSize: 12,
                  color: BarterlyColors.inkMuted,
                ),
              ),
            ),
          ),
        ),
        if (_moved)
          Positioned(
            top: 64,
            left: 0,
            right: 0,
            child: Center(
              child: FilledButton.icon(
                onPressed: _searchHere,
                icon: const Icon(Icons.search),
                label: const Text('Search this area'),
              ),
            ),
          ),
        if (_selected case final gig?)
          Positioned(
            left: 12,
            right: 12,
            bottom: 44,
            child: _SelectedGig(gig: gig, onOpen: () => widget.onOpen(gig)),
          ),
        const Positioned(right: 0, bottom: 0, child: OsmAttribution()),
      ],
    );
  }
}

/// The "© OpenStreetMap contributors" credit, always visible, linking to the
/// copyright page as the tile policy requires.
class OsmAttribution extends ConsumerWidget {
  const new({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) => Material(
    color: BarterlyColors.surface.withValues(alpha: 0.92),
    borderRadius: const BorderRadius.only(topLeft: Radius.circular(8)),
    child: Semantics(
      link: true,
      label: 'Map data © OpenStreetMap contributors. Opens the copyright page.',
      excludeSemantics: true,
      child: InkWell(
        onTap: () =>
            unawaited(ref.read(urlOpenerProvider).openExternal(osmCopyright)),
        child: const Padding(
          padding: EdgeInsets.symmetric(horizontal: 8, vertical: 6),
          child: Text(
            '© OpenStreetMap contributors',
            style: TextStyle(
              fontSize: 12,
              color: BarterlyColors.ink,
              decoration: TextDecoration.underline,
            ),
          ),
        ),
      ),
    ),
  );
}

class _GigPin extends StatelessWidget {
  const new({required this.gig, required this.selected, required this.onTap});

  final Gig gig;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Semantics(
    button: true,
    label: '${gig.title}, ${gig.property.place}',
    excludeSemantics: true,
    child: GestureDetector(
      onTap: onTap,
      child: Center(
        child: Container(
          width: selected ? 40 : 34,
          height: selected ? 40 : 34,
          decoration: BoxDecoration(
            color: selected ? BarterlyColors.ink : BarterlyColors.accent,
            shape: BoxShape.circle,
            border: Border.all(color: BarterlyColors.surface, width: 2),
          ),
          child: const Icon(
            Icons.home_work_outlined,
            size: 18,
            color: BarterlyColors.onAccent,
          ),
        ),
      ),
    ),
  );
}

class _ClusterBubble extends StatelessWidget {
  const new({required this.count, required this.onTap});

  final int count;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Semantics(
    button: true,
    label: '$count gigs here. Zoom in.',
    excludeSemantics: true,
    child: GestureDetector(
      onTap: onTap,
      child: Container(
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: BarterlyColors.accentSoft,
          shape: BoxShape.circle,
          border: Border.all(color: BarterlyColors.accent, width: 2),
        ),
        child: Text(
          '$count',
          style: const TextStyle(
            fontWeight: FontWeight.w700,
            color: BarterlyColors.onAccentSoft,
          ),
        ),
      ),
    ),
  );
}

class _SelectedGig extends StatelessWidget {
  const new({required this.gig, required this.onOpen});

  final Gig gig;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    final colors = payModelColors(gig.payModel);
    return SurfaceCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        spacing: 6,
        children: [
          Row(
            spacing: 8,
            children: [
              Tag(
                label: gig.payModel?.label ?? 'Gig',
                background: colors.background,
                foreground: colors.foreground,
              ),
              Tag(label: '${gig.fit.score}% fit', outlined: true),
            ],
          ),
          Text(gig.title, style: Theme.of(context).textTheme.titleMedium),
          Text(
            gig.property.place,
            style: const TextStyle(color: BarterlyColors.inkMuted),
          ),
          Align(
            alignment: Alignment.centerRight,
            child: FilledButton(
              onPressed: onOpen,
              child: const Text('View gig'),
            ),
          ),
        ],
      ),
    );
  }
}
