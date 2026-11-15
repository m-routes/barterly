import 'dart:async';
import 'dart:math';

import 'package:barterly/src/chat/chat_models.dart';
import 'package:barterly/src/chat/chat_repository.dart';

/// How the chat screen gets and sends messages. The screen only uses this, so
/// [PollingChatTransport] can be swapped for a WebSocket one without changing
/// it.
abstract interface class ChatTransport {
  /// The newest page, or the page before [before].
  Future<MessageBatch> history(String conversationId, {int? before});

  /// Messages after [cursor], for as long as the stream is listened to.
  Stream<MessageBatch> watch(String conversationId, int cursor);

  Future<SendResult> send(
    String conversationId, {
    required String body,
    required String clientId,
    List<String> attachmentIds,
  });

  Future<void> markRead(String conversationId, int upTo);
}

/// Short polling over REST: asks for messages after the cursor every few
/// seconds, only while someone listens (the chat screen is open). Backs off
/// after failures and polls straight away after a send.
class PollingChatTransport implements ChatTransport {
  new(this._repository, {this.interval = const Duration(seconds: 4)});

  static const maxBackoff = Duration(seconds: 30);

  final ChatRepository _repository;
  final Duration interval;
  final Map<String, void Function()> _wake = {};

  @override
  Future<MessageBatch> history(String conversationId, {int? before}) =>
      _repository.messages(conversationId, before: before);

  @override
  Stream<MessageBatch> watch(String conversationId, int cursor) {
    Timer? timer;
    var current = cursor;
    var delay = interval;
    var stopped = false;
    var inFlight = false;
    late final StreamController<MessageBatch> controller;
    late final Future<void> Function() tick;

    void schedule(Duration after) {
      if (stopped) return;
      timer?.cancel();
      timer = Timer(after, () => unawaited(tick()));
    }

    tick = () async {
      if (stopped || inFlight) return;
      inFlight = true;
      try {
        final batch = await _repository.messages(
          conversationId,
          after: current,
        );
        if (stopped) return;
        current = batch.cursor;
        delay = interval;
        controller.add(batch);
      } on Object catch (error) {
        if (stopped) return;
        delay = Duration(
          milliseconds: min(
            delay.inMilliseconds * 2,
            maxBackoff.inMilliseconds,
          ),
        );
        controller.addError(error);
      } finally {
        inFlight = false;
      }
      schedule(delay);
    };

    controller = StreamController<MessageBatch>(
      onListen: () {
        _wake[conversationId] = () => schedule(Duration.zero);
        schedule(interval);
      },
      onCancel: () {
        stopped = true;
        timer?.cancel();
        _wake.remove(conversationId);
      },
    );
    return controller.stream;
  }

  @override
  Future<SendResult> send(
    String conversationId, {
    required String body,
    required String clientId,
    List<String> attachmentIds = const [],
  }) async {
    final result = await _repository.send(
      conversationId,
      body: body,
      clientId: clientId,
      attachmentIds: attachmentIds,
    );
    _wake[conversationId]?.call();
    return result;
  }

  @override
  Future<void> markRead(String conversationId, int upTo) =>
      _repository.markRead(conversationId, upTo);
}
