import 'dart:async';

import 'package:barterly/src/providers.dart';
import 'package:barterly/src/theme/tokens.dart';
import 'package:barterly/src/update/app_version.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';
import 'package:package_info_plus/package_info_plus.dart';

/// This install's version, from the platform (tests override it).
final installedAppProvider = FutureProvider<InstalledApp>((ref) async {
  final info = await PackageInfo.fromPlatform();
  return InstalledApp(
    version: info.version,
    buildNumber: info.buildNumber,
    platform: kIsWeb ? '' : platformName(defaultTargetPlatform),
  );
});

final versionRepositoryProvider = Provider<VersionRepository>(
  (ref) => VersionRepository(ref.watch(dioProvider)),
);

@immutable
class UpdateState {
  const new({this.need = UpdateNeed.none, this.policy, this.dismissed = false});

  final UpdateNeed need;
  final UpdatePolicy? policy;

  /// The person chose "Later" for this latest version.
  final bool dismissed;
}

/// Whether this version must or may be updated (docs/api-versioning.md):
/// - on launch, [check] asks GET /api/v1/app/version/;
/// - any call answered 426 `upgrade_required` makes it [UpdateNeed.required]
///   (ClientVersionInterceptor), even if the launch check failed.
class UpdateController extends Notifier<UpdateState> {
  static const dismissedKey = 'update.dismissed.v1';

  @override
  UpdateState build() => const UpdateState();

  Future<void> check() async {
    try {
      final app = await ref.read(installedAppProvider.future);
      if (app.platform.isEmpty) return;
      final policy = await ref.read(versionRepositoryProvider).fetch(app);
      // A 426 that arrived meanwhile has the last word.
      if (state.need == UpdateNeed.required) return;
      final need = policy.needFor(app.version);
      var dismissed = false;
      if (need == UpdateNeed.available) {
        final saved = await ref
            .read(keyValueStoreProvider)
            .readJson(dismissedKey);
        dismissed = saved?['version'] == policy.latestVersion;
      }
      state = UpdateState(need: need, policy: policy, dismissed: dismissed);
    } on Object {
      // Offline, or a server without the endpoint: carry on. The server still
      // answers 426 to an unsupported version, which blocks then.
    }
  }

  void upgradeRequired(UpdatePolicy policy) =>
      state = UpdateState(need: UpdateNeed.required, policy: policy);

  /// "Later" on the optional update: hidden until a newer version ships.
  Future<void> later() async {
    final policy = state.policy;
    state = UpdateState(need: state.need, policy: policy, dismissed: true);
    if (policy != null) {
      await ref.read(keyValueStoreProvider).writeJson(dismissedKey, {
        'version': policy.latestVersion,
      });
    }
  }
}

final updateProvider = NotifierProvider<UpdateController, UpdateState>(
  UpdateController.new,
);

/// Wraps the whole app (MaterialApp.builder): a blocking screen when this
/// version is no longer supported, a dismissible card when a newer one exists.
class UpdateGate extends ConsumerStatefulWidget {
  const new({required this.child, super.key});

  final Widget child;

  @override
  ConsumerState<UpdateGate> createState() => _UpdateGateState();
}

class _UpdateGateState extends ConsumerState<UpdateGate> {
  @override
  void initState() {
    super.initState();
    unawaited(Future.microtask(ref.read(updateProvider.notifier).check));
  }

  Future<void> _openStore(UpdatePolicy? policy) async {
    final url = Uri.tryParse(policy?.storeUrl ?? '');
    if (url == null || !url.hasScheme) return;
    await ref.read(urlOpenerProvider).openExternal(url);
  }

  @override
  Widget build(BuildContext context) {
    final update = ref.watch(updateProvider);
    if (update.need == UpdateNeed.required) {
      return ForceUpdateScreen(
        policy: update.policy,
        onUpdate: () => _openStore(update.policy),
      );
    }
    final offer = update.need == UpdateNeed.available && !update.dismissed;
    return Stack(
      children: [
        widget.child,
        if (offer)
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: SafeArea(
              child: _UpdateAvailableCard(
                onUpdate: () => _openStore(update.policy),
                onLater: () =>
                    unawaited(ref.read(updateProvider.notifier).later()),
              ),
            ),
          ),
      ],
    );
  }
}

class ForceUpdateScreen extends StatelessWidget {
  const new({required this.policy, required this.onUpdate, super.key});

  final UpdatePolicy? policy;
  final VoidCallback onUpdate;

  @override
  Widget build(BuildContext context) {
    final message = policy?.message ?? '';
    final canOpenStore = (policy?.storeUrl ?? '').isNotEmpty;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(BarterlySpace.lg),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              spacing: BarterlySpace.md,
              children: [
                const Icon(Icons.system_update_outlined, size: 48),
                Semantics(
                  header: true,
                  child: Text(
                    'Update Barterly to continue',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.headlineSmall,
                  ),
                ),
                Text(
                  message.isNotEmpty
                      ? message
                      : 'This version of the app no longer works with '
                            'Barterly. Your applications, trips and wallet '
                            'are safe: update to pick up where you left off.',
                  textAlign: TextAlign.center,
                ),
                if (canOpenStore)
                  FilledButton(
                    onPressed: onUpdate,
                    child: const Text('Update now'),
                  )
                else
                  const Text(
                    'Update from your app store.',
                    textAlign: TextAlign.center,
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _UpdateAvailableCard extends StatelessWidget {
  const new({required this.onUpdate, required this.onLater});

  final VoidCallback onUpdate;
  final VoidCallback onLater;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.fromLTRB(12, 0, 12, 76),
    child: Material(
      elevation: 6,
      borderRadius: BorderRadius.circular(BarterlyRadius.md),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 8, 8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Semantics(
              liveRegion: true,
              child: const Text('A new version of Barterly is available.'),
            ),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                TextButton(onPressed: onLater, child: const Text('Later')),
                TextButton(onPressed: onUpdate, child: const Text('Update')),
              ],
            ),
          ],
        ),
      ),
    ),
  );
}
