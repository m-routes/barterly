/// A help or feedback request (backend apps/support).
class SupportTicket {
  const new({
    required this.id,
    required this.reference,
    required this.kind,
    required this.subject,
    required this.status,
    required this.lastMessageAt,
    this.replyExpectedBy,
    this.messages = const [],
  });

  factory fromJson(Map<String, Object?> json) => SupportTicket(
    id: json['id']! as String,
    reference: json['reference']! as String,
    kind: json['kind']! as String,
    subject: json['subject']! as String,
    status: json['status']! as String,
    lastMessageAt: DateTime.parse(json['last_message_at']! as String),
    replyExpectedBy: switch (json['reply_expected_by']) {
      final String at => DateTime.parse(at),
      _ => null,
    },
    messages: [
      for (final m in (json['messages'] as List<Object?>?) ?? const [])
        SupportMessage.fromJson(m! as Map<String, Object?>),
    ],
  );

  final String id;
  final String reference;
  final String kind;
  final String subject;
  final String status;
  final DateTime lastMessageAt;
  final DateTime? replyExpectedBy;
  final List<SupportMessage> messages;

  String get statusLabel => switch (status) {
    'open' => 'Waiting for us',
    'waiting' => "We've answered",
    'resolved' => 'Resolved',
    _ => status,
  };
}

class SupportMessage {
  const new({required this.fromStaff, required this.body, required this.at});

  factory fromJson(Map<String, Object?> json) => SupportMessage(
    fromStaff: json['from_staff']! as bool,
    body: json['body']! as String,
    at: DateTime.parse(json['created_at']! as String),
  );

  final bool fromStaff;
  final String body;
  final DateTime at;
}

/// What people can write to us about, in the order the form lists them.
const supportKinds = <(String, String, String)>[
  ('help', 'Help with something', 'We answer within a day.'),
  (
    'payment',
    'Money or payments',
    'Urgent: we answer within 2 hours, 8am to 10pm.',
  ),
  (
    'safety',
    'A safety concern',
    'Urgent: we answer within 2 hours, 8am to 10pm. In danger now? Call 112.',
  ),
  ('bug', "Something isn't working", 'We answer within a day.'),
  ('feedback', 'Feedback or an idea', 'We read every one, within 3 days.'),
];
