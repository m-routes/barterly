/// How a talent is compensated for a listing.
enum PayModel {
  volunteer('Volunteer', 'Work for stay'),
  barter('Barter', 'Content for stay'),
  hybrid('Hybrid', 'Stay plus stipend'),
  paid('Paid', 'Paid role');

  new(this.label, this.summary);

  final String label;
  final String summary;

  String get description => '$label: $summary';
}
