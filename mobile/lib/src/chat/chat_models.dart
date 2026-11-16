import 'package:flutter/foundation.dart';

/// A chat message (backend apps/chat/serializers.py ChatMessageSerializer).
@immutable
class ChatMessage {
  const new({
    required this.id,
    required this.cursor,
    required this.mine,
    required this.body,
    required this.createdAt,
    this.masked = false,
    this.attachments = const [],
    this.clientId = '',
  });

  factory fromJson(Map<String, Object?> json) => ChatMessage(
    id: json['id']! as String,
    cursor: int.tryParse('${json['cursor']}') ?? 0,
    mine: json['mine'] as bool? ?? false,
    body: json['body'] as String? ?? '',
    masked: json['masked'] as bool? ?? false,
    createdAt:
        DateTime.tryParse(json['created_at'] as String? ?? '') ??
        DateTime.now(),
    clientId: json['client_id'] as String? ?? '',
    attachments: [
      for (final a in (json['attachments'] as List?) ?? const [])
        if (a is Map<String, Object?>) ChatAttachment.fromJson(a),
    ],
  );

  final String id;

  /// Increasing within a conversation; the polling cursor.
  final int cursor;
  final bool mine;
  final String body;

  /// Contact details in it were hidden.
  final bool masked;
  final DateTime createdAt;
  final List<ChatAttachment> attachments;
  final String clientId;
}

@immutable
class ChatAttachment {
  const new({required this.id, required this.isImage, this.url});

  factory fromJson(Map<String, Object?> json) => ChatAttachment(
    id: json['id']! as String,
    isImage: json['kind'] == 'image',
    url: json['url'] as String?,
  );

  final String id;
  final bool isImage;
  final String? url;
}

/// Messages after a cursor, or a page of history.
@immutable
class MessageBatch {
  const new({
    required this.messages,
    required this.cursor,
    this.otherReadUpTo = 0,
    this.hasEarlier = false,
  });

  factory fromJson(Map<String, Object?> json) => MessageBatch(
    messages: [
      for (final m in (json['results'] as List?) ?? const [])
        if (m is Map<String, Object?>) ChatMessage.fromJson(m),
    ],
    cursor: int.tryParse('${json['cursor']}') ?? 0,
    otherReadUpTo: int.tryParse('${json['other_read_up_to']}') ?? 0,
    hasEarlier: json['has_earlier'] as bool? ?? false,
  );

  final List<ChatMessage> messages;
  final int cursor;

  /// The newest of my messages the other side has read.
  final int otherReadUpTo;
  final bool hasEarlier;
}

@immutable
class SendResult {
  const new({required this.message, this.notice = ''});

  final ChatMessage message;

  /// Shown to the sender when not empty (why something was hidden).
  final String notice;
}

/// A conversation as the chat screen needs it.
@immutable
class Conversation {
  const new({
    required this.id,
    required this.applicationId,
    required this.otherName,
    required this.gigTitle,
    this.canSend = true,
    this.cantSendReason = '',
    this.contactSharingAllowed = false,
    this.blockedByMe = false,
  });

  factory fromJson(Map<String, Object?> json) => Conversation(
    id: json['id']! as String,
    applicationId: json['application'] as String? ?? '',
    otherName: (json['other'] as Map?)?['name'] as String? ?? 'Host',
    gigTitle: json['gig_title'] as String? ?? '',
    canSend: json['can_send'] as bool? ?? true,
    cantSendReason: json['cant_send_reason'] as String? ?? '',
    contactSharingAllowed: json['contact_sharing_allowed'] as bool? ?? false,
    blockedByMe: json['blocked_by_me'] as bool? ?? false,
  );

  final String id;
  final String applicationId;
  final String otherName;
  final String gigTitle;
  final bool canSend;
  final String cantSendReason;
  final bool contactSharingAllowed;
  final bool blockedByMe;
}

/// Why a message is reported (backend apps/chat/models.py ReportReason).
enum ReportReason {
  spam('spam', 'Spam'),
  harassment('harassment', 'Harassment or abuse'),
  scam('scam', 'Scam or fraud'),
  contactSharing('contact_sharing', 'Asking to move off Barterly'),
  inappropriate('inappropriate', 'Inappropriate content'),
  other('other', 'Something else');

  new(this.value, this.label);

  final String value;
  final String label;
}

/// Merge [incoming] into [current]: no duplicates, oldest first.
List<ChatMessage> mergeMessages(
  List<ChatMessage> current,
  Iterable<ChatMessage> incoming,
) {
  final byId = {for (final m in current) m.id: m};
  for (final m in incoming) {
    byId[m.id] = m;
  }
  return byId.values.toList()..sort((a, b) => a.cursor.compareTo(b.cursor));
}
