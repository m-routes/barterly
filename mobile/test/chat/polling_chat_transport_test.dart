import 'package:barterly/src/chat/chat_models.dart';
import 'package:barterly/src/chat/chat_repository.dart';
import 'package:barterly/src/chat/chat_transport.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

ChatMessage message(int cursor, {bool mine = false}) => ChatMessage(
  id: 'm$cursor',
  cursor: cursor,
  mine: mine,
  body: 'hello $cursor',
  createdAt: DateTime.utc(2026, 11, 15),
);

/// Answers polls from a queue and records each `after` cursor.
class FakeChatRepository extends ChatRepository {
  new() : super(Dio());

  final List<MessageBatch> pages = [];
  final List<int?> polledAfter = [];
  Exception? failWith;

  @override
  Future<MessageBatch> messages(String id, {int? after, int? before}) async {
    polledAfter.add(after);
    if (failWith != null) throw failWith!;
    return pages.isEmpty
        ? MessageBatch(messages: const [], cursor: after ?? 0)
        : pages.removeAt(0);
  }

  @override
  Future<SendResult> send(
    String id, {
    required String body,
    required String clientId,
    List<String> attachmentIds = const [],
  }) async => SendResult(message: message(9, mine: true));
}

const tick = Duration(milliseconds: 40);

Future<void> wait(int ticks) => Future<void>.delayed(tick * ticks);

void main() {
  test(
    'polls after the cursor, moves it forward, stops when cancelled',
    () async {
      final repo = FakeChatRepository()
        ..pages.add(
          MessageBatch(messages: [message(3), message(4)], cursor: 4),
        );
      final transport = PollingChatTransport(repo, interval: tick * 2);
      final got = <MessageBatch>[];
      final sub = transport.watch('c1', 2).listen(got.add);

      expect(repo.polledAfter, isEmpty, reason: 'waits one interval first');
      await wait(3);
      expect(repo.polledAfter.first, 2);
      expect(got.first.messages.map((m) => m.cursor), [3, 4]);
      await wait(2);
      expect(repo.polledAfter.skip(1).first, 4);

      await sub.cancel();
      final polls = repo.polledAfter.length;
      await wait(6);
      expect(repo.polledAfter, hasLength(polls));
    },
  );

  test('backs off after errors and reports them', () async {
    final repo = FakeChatRepository()..failWith = Exception('offline');
    final transport = PollingChatTransport(repo, interval: tick);
    var errors = 0;
    final sub = transport
        .watch('c1', 0)
        .listen((_) {}, onError: (_) => errors++);
    // Polls at 1, then 1+2, then 1+2+4 ticks: three in seven ticks, not seven.
    await wait(8);
    await sub.cancel();
    expect(repo.polledAfter, hasLength(3));
    expect(errors, 3);
  });

  test('polls straight away after a send', () async {
    final repo = FakeChatRepository();
    final transport = PollingChatTransport(
      repo,
      interval: const Duration(minutes: 1),
    );
    final sub = transport.watch('c1', 0).listen((_) {});
    await transport.send('c1', body: 'hi', clientId: 'x');
    await wait(1);
    expect(repo.polledAfter, [0]);
    await sub.cancel();
  });

  test('merging keeps one copy of each message, oldest first', () {
    final merged = mergeMessages(
      [message(2), message(1)],
      [message(3), message(2)],
    );
    expect(merged.map((m) => m.cursor), [1, 2, 3]);
  });
}
