import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/chat/chat_models.dart';
import 'package:dio/dio.dart';

/// The chat REST calls (backend apps/chat/views.py).
class ChatRepository {
  new(this._dio);

  final Dio _dio;

  String _c(String id) => '/api/v1/conversations/$id/';

  Future<Conversation> conversation(String id) => guardApi(() async {
    final response = await _dio.get<Map<String, Object?>>(_c(id));
    return Conversation.fromJson(response.data!);
  });

  /// Messages after [after] (polling), before [before] (history), or the
  /// newest page.
  Future<MessageBatch> messages(String id, {int? after, int? before}) =>
      guardApi(() async {
        final response = await _dio.get<Map<String, Object?>>(
          '${_c(id)}messages/',
          queryParameters: {'after': ?after, 'before': ?before},
        );
        return MessageBatch.fromJson(response.data!);
      });

  Future<SendResult> send(
    String id, {
    required String body,
    required String clientId,
    List<String> attachmentIds = const [],
  }) => guardApi(() async {
    final response = await _dio.post<Map<String, Object?>>(
      '${_c(id)}messages/',
      data: {
        'body': body,
        'client_id': clientId,
        'attachment_ids': attachmentIds,
      },
    );
    final data = response.data!;
    return SendResult(
      message: ChatMessage.fromJson(data['message']! as Map<String, Object?>),
      notice: data['notice'] as String? ?? '',
    );
  });

  Future<void> markRead(String id, int upTo) => guardApi(() async {
    await _dio.post<Object?>('${_c(id)}read/', data: {'up_to': '$upTo'});
  });

  Future<Conversation> setBlocked(String id, {required bool blocked}) =>
      guardApi(() async {
        final url = '${_c(id)}block/';
        final response = blocked
            ? await _dio.post<Map<String, Object?>>(url)
            : await _dio.delete<Map<String, Object?>>(url);
        return Conversation.fromJson(response.data!);
      });

  Future<void> report(String messageId, ReportReason reason) =>
      guardApi(() async {
        await _dio.post<Object?>(
          '/api/v1/messages/$messageId/report/',
          data: {'reason': reason.value},
        );
      });
}
