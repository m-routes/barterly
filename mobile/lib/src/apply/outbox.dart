import 'dart:async';

import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/apply/application.dart';
import 'package:barterly/src/apply/applications_repository.dart';
import 'package:barterly/src/platform/device_keys.dart';
import 'package:barterly/src/platform/media_picker.dart';
import 'package:barterly/src/providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// What happened when a draft was sent.
sealed class SendOutcome {
  const new(this.draft);

  /// The draft with any uploads done so far recorded.
  final ApplicationDraft draft;
}

final class Sent extends SendOutcome {
  const new(super.draft, this.application);
  final Application application;
}

/// No network: nothing was lost, try again later.
final class Offline extends SendOutcome {
  const new(super.draft);
}

/// The API refused it: [reasons] from a 422, or [error] for anything else.
final class Refused extends SendOutcome {
  const new(super.draft, this.error, this.reasons);
  final ApiError error;
  final List<BlockedReason> reasons;

  List<String> get messages => reasons.isNotEmpty
      ? [for (final r in reasons) r.message]
      : error.isValidation && error.fieldErrors.isNotEmpty
      ? error.fieldErrors.values.toList()
      : [error.userMessage];
}

/// Uploads a draft's files, then applies.
///
/// Uploads that succeed are kept on the returned draft, so a retry after a
/// dropped connection doesn't upload them again.
class ApplicationSender {
  new({
    required this._picker,
    required this._uploader,
    required this._applications,
  });

  final MediaPicker _picker;
  final MediaUploader _uploader;
  final ApplicationsRepository _applications;

  Future<SendOutcome> send(
    ApplicationDraft draft, {
    void Function(int done, int total)? onProgress,
  }) async {
    var current = draft;
    final files = draft.attachments.where((a) => !a.isLink).length;
    var uploaded = draft.attachments
        .where((a) => !a.isLink && a.mediaId != null)
        .length;
    onProgress?.call(uploaded, files);
    try {
      for (final (i, attachment) in draft.attachments.indexed) {
        if (attachment.isLink || attachment.mediaId != null) continue;
        final bytes = await _readFile(attachment);
        final mediaId = await _uploader.upload(
          kind: attachment.kind,
          contentType: attachment.contentType!,
          bytes: bytes,
        );
        current = current.copyWith(
          attachments: [...current.attachments]
            ..[i] = attachment.withMediaId(mediaId),
        );
        onProgress?.call(++uploaded, files);
      }
      final application = await _applications.apply(
        current.gigId,
        current.toApi(),
      );
      // Sent: the kept copies of the files aren't needed any more.
      for (final a in current.attachments) {
        if (a.localPath != null) unawaited(_picker.discard(a.localPath!));
      }
      return Sent(current, application);
    } on ApiError catch (error) {
      if (error.code == 'network_error' || error.status == 503) {
        return Offline(current);
      }
      return Refused(current, error, blockedReasons(error));
    }
  }

  Future<List<int>> _readFile(AttachmentDraft attachment) async {
    try {
      return await _picker.read(attachment.localPath!);
    } on Object {
      throw const ApiError(
        status: 0,
        code: 'attachment_missing',
        message:
            'One of your files is no longer on this phone. Remove it and '
            'add it again.',
      );
    }
  }
}

final applicationSenderProvider = Provider<ApplicationSender>(
  (ref) => ApplicationSender(
    picker: ref.watch(mediaPickerProvider),
    uploader: ref.watch(mediaUploaderProvider),
    applications: ref.watch(applicationsRepositoryProvider),
  ),
);

final outboxProvider = NotifierProvider<Outbox, List<ApplicationDraft>>(
  Outbox.new,
);

/// Applications written offline, sent in order when the network returns.
///
/// Persisted, so a queued application survives the app being closed.
class Outbox extends Notifier<List<ApplicationDraft>> {
  Future<void>? _running;
  Future<void>? _loaded;
  late String _key;

  @override
  List<ApplicationDraft> build() {
    // Per account: another account's drafts are never shown or sent.
    _key = DeviceKeys.outbox(ref.watch(currentUserIdProvider));
    _running = null;
    ref.listen(onlineProvider, (previous, next) {
      if (next.value == true && previous?.value != true) unawaited(flush());
    });
    _loaded = _load();
    return const [];
  }

  Future<void> _load() async {
    final json = await ref.read(keyValueStoreProvider).readJson(_key);
    final drafts = [
      for (final d in (json?['drafts'] as List?) ?? const [])
        if (d is Map<String, Object?>) _parse(d),
    ].nonNulls.toList();
    if (!ref.mounted) return;
    state = drafts;
    if (drafts.any((d) => d.status == DraftStatus.queued)) unawaited(flush());
  }

  ApplicationDraft? _parse(Map<String, Object?> json) {
    try {
      return ApplicationDraft.fromJson(json);
    } on Object {
      return null;
    }
  }

  Future<void> _save() => ref.read(keyValueStoreProvider).writeJson(_key, {
    'drafts': [for (final d in state) d.toJson()],
  });

  void _put(ApplicationDraft draft) {
    state = [
      for (final d in state)
        if (d.localId == draft.localId) draft else d,
    ];
  }

  /// Keeps [draft] until it can be sent.
  Future<void> enqueue(ApplicationDraft draft) async {
    await _loaded;
    state = [
      ...state.where((d) => d.localId != draft.localId),
      draft.copyWith(status: DraftStatus.queued, problems: const []),
    ];
    await _save();
  }

  Future<void> remove(String localId) async {
    await _loaded;
    final draft = state.where((d) => d.localId == localId).firstOrNull;
    state = state.where((d) => d.localId != localId).toList();
    await _save();
    final picker = ref.read(mediaPickerProvider);
    for (final a in draft?.attachments ?? const <AttachmentDraft>[]) {
      if (a.localPath != null) unawaited(picker.discard(a.localPath!));
    }
  }

  /// Try a draft that needed attention again (after fixing the profile, say).
  Future<void> retry(String localId) async {
    final draft = state.where((d) => d.localId == localId).firstOrNull;
    if (draft == null) return;
    _put(draft.copyWith(status: DraftStatus.queued, problems: const []));
    await _save();
    await flush();
  }

  /// Sends every queued draft, oldest first. Stops at the first sign of no
  /// network; refused drafts stay, marked for the talent to look at.
  ///
  /// A call while a flush is running waits for it, then sends anything
  /// queued in the meantime.
  Future<void> flush() async {
    await _loaded;
    while (_running != null) {
      await _running;
    }
    if (!ref.mounted) return;
    final run = _flush();
    _running = run;
    try {
      await run;
    } finally {
      if (identical(_running, run)) _running = null;
    }
  }

  Future<void> _flush() async {
    var sentAny = false;
    final tried = <String>{};
    try {
      while (ref.mounted) {
        final draft = state
            .where(
              (d) =>
                  d.status == DraftStatus.queued && !tried.contains(d.localId),
            )
            .firstOrNull;
        if (draft == null) return;
        tried.add(draft.localId);
        _put(draft.copyWith(status: DraftStatus.sending));
        final outcome = await ref.read(applicationSenderProvider).send(draft);
        if (!ref.mounted) return;
        switch (outcome) {
          case Sent():
            state = state.where((d) => d.localId != draft.localId).toList();
            sentAny = true;
          case Offline(:final draft):
            _put(draft.copyWith(status: DraftStatus.queued));
            await _save();
            return;
          case final Refused refused:
            _put(
              refused.draft.copyWith(
                status: DraftStatus.needsAttention,
                problems: refused.messages,
              ),
            );
        }
        await _save();
      }
    } finally {
      if (sentAny && ref.mounted) ref.invalidate(myApplicationsProvider);
    }
  }
}

/// The talent's applications on the API.
final FutureProvider<List<Application>> myApplicationsProvider =
    FutureProvider.autoDispose<List<Application>>(
      (ref) => ref.watch(applicationsRepositoryProvider).mine(),
    );
