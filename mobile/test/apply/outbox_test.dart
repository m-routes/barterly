import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/api/token_store.dart';
import 'package:barterly/src/apply/application.dart';
import 'package:barterly/src/apply/outbox.dart';
import 'package:barterly/src/platform/device_keys.dart';
import 'package:barterly/src/platform/key_value_store.dart';
import 'package:barterly/src/platform/network_status.dart';
import 'package:barterly/src/providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import '../fixtures.dart';
import '../helpers.dart';

ApplicationDraft draft({
  String localId = 'd1',
  List<AttachmentDraft> attachments = const [],
}) => ApplicationDraft(
  localId: localId,
  gigId: 'g1',
  gigTitle: 'Reception volunteer',
  pitch: ' I ran a hostel desk in Manali. ',
  answers: const ['Yes '],
  proposedStart: DateTime(2026, 12, 12),
  proposedEnd: DateTime(2026, 12, 26),
  attachments: attachments,
  createdAt: DateTime.utc(2026, 11, 14),
);

const photo = AttachmentDraft(
  kind: AttachmentKind.photo,
  localPath: '/kept/mural.jpg',
  contentType: 'image/jpeg',
  sizeBytes: 3,
  title: 'mural.jpg',
);

const link = AttachmentDraft(
  kind: AttachmentKind.link,
  url: 'https://example.com/reel',
);

/// An API that accepts uploads and applications, counting each step.
FakeApi uploadingApi({Handler? onApply}) => FakeApi({
  'POST /api/v1/media/upload-url/': (_) =>
      FakeResponse(201, uploadTicket('m1')),
  'PUT https://storage.test/upload/m1': (_) => const FakeResponse(200),
  'POST /api/v1/media/confirm/': (_) => ok({'id': 'm1', 'status': 'ready'}),
  'POST /api/v1/gigs/g1/applications/':
      onApply ?? (_) => FakeResponse(201, applicationJson(attachments: 2)),
});

final String outboxKey = DeviceKeys.outbox('u1');

void main() {
  late FakeMediaPicker picker;
  late MemoryKeyValueStore store;
  late FakeNetworkStatus network;

  setUp(() {
    picker = FakeMediaPicker()..files['/kept/mural.jpg'] = [0xff, 0xd8, 0xff];
    store = MemoryKeyValueStore();
    network = FakeNetworkStatus(online: false);
  });

  ProviderContainer containerFor(FakeApi api) => ProviderContainer.test(
    retry: (_, _) => null,
    overrides: [
      ...testOverrides(
        api: api,
        tokens: MemoryTokenStore(signedInTokens),
        store: store,
        network: network,
        picker: picker,
      ),
      currentUserIdProvider.overrideWithValue('u1'),
    ],
  );

  Future<void> settle() async {
    for (var i = 0; i < 20; i++) {
      await Future<void>.delayed(Duration.zero);
    }
  }

  test('the API body trims text and lists attachments', () {
    final body = draft(attachments: [photo.withMediaId('m1'), link]).toApi();
    expect(body, {
      'pitch': 'I ran a hostel desk in Manali.',
      'answers': ['Yes'],
      'proposed_start': '2026-12-12',
      'proposed_end': '2026-12-26',
      'attachments': [
        {'kind': 'photo', 'media_id': 'm1', 'title': 'mural.jpg'},
        {'kind': 'link', 'url': 'https://example.com/reel'},
      ],
    });
  });

  test('a draft survives a JSON round trip; mid-send goes back to queued', () {
    final sending = draft(attachments: [photo, link])
        .copyWith(status: DraftStatus.sending);
    final restored = ApplicationDraft.fromJson(sending.toJson());
    expect(restored.status, DraftStatus.queued);
    expect(restored.toApi()['attachments'], hasLength(2));
    expect(restored.attachments.first.localPath, '/kept/mural.jpg');
  });

  test('422 reasons are read from details', () {
    const error = ApiError(
      status: 422,
      code: 'application_blocked',
      message: "You can't apply to this gig yet.",
      details: {
        'reasons': [
          {'code': 'verification_required', 'message': 'Needs a verified ID.'},
          {'code': 'stay_too_short', 'message': 'Stay at least 14 days.'},
        ],
      },
    );
    expect(
      [for (final r in blockedReasons(error)) r.code],
      ['verification_required', 'stay_too_short'],
    );
  });

  test('queued offline, sent when the network returns', () async {
    final api = uploadingApi();
    final container = containerFor(api)..listen(outboxProvider, (_, _) {});
    await container
        .read(outboxProvider.notifier)
        .enqueue(draft(attachments: [photo, link]));
    await settle();

    expect(container.read(outboxProvider).single.status, DraftStatus.queued);
    expect(
      store.data[outboxKey]?['drafts'],
      hasLength(1),
      reason: 'kept on the device in case the app closes',
    );
    expect(api.calls, isEmpty);

    network.online = true;
    await settle();
    await container.read(outboxProvider.notifier).flush();

    expect(api.calls, [
      'POST /api/v1/media/upload-url/',
      'PUT https://storage.test/upload/m1',
      'POST /api/v1/media/confirm/',
      'POST /api/v1/gigs/g1/applications/',
    ]);
    final apply = api.requests.last.data as Map;
    expect(apply['attachments'], [
      {'kind': 'photo', 'media_id': 'm1', 'title': 'mural.jpg'},
      {'kind': 'link', 'url': 'https://example.com/reel'},
    ]);
    expect(container.read(outboxProvider), isEmpty);
    expect(store.data[outboxKey]?['drafts'], isEmpty);
    expect(picker.discarded, ['/kept/mural.jpg']);
  });

  test("a dropped connection mid-send keeps uploads, so they aren't "
      'repeated', () async {
    // The upload works, then the POST is cut off (no response at all).
    final api = uploadingApi(
      onApply: (_) => throw StateError('connection dropped'),
    );
    network.online = true;
    final container = containerFor(api)..listen(outboxProvider, (_, _) {});
    await container
        .read(outboxProvider.notifier)
        .enqueue(draft(attachments: [photo]));
    await container.read(outboxProvider.notifier).flush();

    final kept = container.read(outboxProvider).single;
    expect(kept.status, DraftStatus.queued);
    expect(kept.attachments.single.mediaId, 'm1');

    api.routes['POST /api/v1/gigs/g1/applications/'] = (_) =>
        FakeResponse(201, applicationJson());
    final before = api.calls.length;
    await container.read(outboxProvider.notifier).flush();
    expect(api.calls.sublist(before), ['POST /api/v1/gigs/g1/applications/']);
    expect(container.read(outboxProvider), isEmpty);
  });

  test('a refused draft waits for the talent with the reasons', () async {
    final api = uploadingApi(
      onApply: (_) => apiError(
        422,
        'application_blocked',
        "You can't apply to this gig yet.",
        {
          'reasons': [
            {'code': 'already_applied', 'message': 'You already applied.'},
          ],
        },
      ),
    );
    network.online = true;
    final container = containerFor(api)..listen(outboxProvider, (_, _) {});
    await container.read(outboxProvider.notifier).enqueue(draft());
    await container.read(outboxProvider.notifier).flush();

    final kept = container.read(outboxProvider).single;
    expect(kept.status, DraftStatus.needsAttention);
    expect(kept.problems, ['You already applied.']);

    // Not retried automatically.
    final before = api.calls.length;
    await container.read(outboxProvider.notifier).flush();
    expect(api.calls.length, before);

    await container.read(outboxProvider.notifier).remove('d1');
    expect(container.read(outboxProvider), isEmpty);
  });

  test('drafts saved by an earlier run are loaded and sent', () async {
    await store.writeJson(outboxKey, {
      'drafts': [draft(localId: 'old').toJson()],
    });
    network.online = true;
    final api = uploadingApi();
    final container = containerFor(api)..listen(outboxProvider, (_, _) {});
    await settle();
    await container.read(outboxProvider.notifier).flush();
    expect(api.calls, ['POST /api/v1/gigs/g1/applications/']);
    expect(container.read(outboxProvider), isEmpty);
  });

  test('the upload PUT carries the signed headers and no API token', () async {
    final api = uploadingApi();
    final container = containerFor(api);
    final id = await container
        .read(mediaUploaderProvider)
        .upload(
          kind: AttachmentKind.photo,
          contentType: 'image/jpeg',
          bytes: const [1, 2, 3],
        );
    expect(id, 'm1');
    final ticket = api.requests[0];
    expect(ticket.data, {
      'kind': 'photo',
      'content_type': 'image/jpeg',
      'size_bytes': 3,
    });
    expect(ticket.headers['Authorization'], 'Bearer access-1');
    final put = api.requests[1];
    expect(put.method, 'PUT');
    expect(put.headers['Authorization'], isNull);
    expect(put.headers['x-goog-meta-owner'], 'u1');
    expect(put.contentType, 'image/jpeg');
    expect(api.requests[2].data, {'media_id': 'm1'});
  });

  test('confirm is retried while storage catches up (409)', () async {
    var confirms = 0;
    final api = uploadingApi();
    api.routes['POST /api/v1/media/confirm/'] = (_) =>
        ++confirms < 2 ? apiError(409, 'upload_not_ready') : ok({'id': 'm1'});
    final container = containerFor(api);
    await container
        .read(mediaUploaderProvider)
        .upload(
          kind: AttachmentKind.document,
          contentType: 'image/png',
          bytes: const [1],
        );
    expect(confirms, 2);
    expect(api.requests.first.data, containsPair('kind', 'document'));
  });
}
