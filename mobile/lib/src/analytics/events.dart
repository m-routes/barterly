/// The product events the app may send. The server keeps only these, with only
/// the listed properties (backend/apps/analytics/events.py; a backend test
/// compares the lists). Never put free text or personal details in a property.
const eventNames = <String>[
  'screen_view',
  'onboarding_step',
  'invite_entered',
  'gig_builder_step',
  'gig_submitted',
  'search',
  'gig_viewed',
  'apply_started',
  'apply_submitted',
  'offer_viewed',
  'help_opened',
  'feedback_sent',
];

final _id = RegExp(
  r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
  caseSensitive: false,
);

/// A route as a screen name, with ids taken out:
/// `/trips/agreement/<uuid>` → `trips/agreement`.
String screenOf(String path) {
  final parts = [
    for (final part in path.split('/'))
      if (part.isNotEmpty && !_id.hasMatch(part) && int.tryParse(part) == null)
        part.toLowerCase().replaceAll(RegExp('[^a-z0-9_-]'), ''),
  ].where((p) => p.isNotEmpty);
  final screen = parts.join('/');
  if (screen.isEmpty) return 'home';
  return screen.length > 60 ? screen.substring(0, 60) : screen;
}
