import 'package:barterly/src/platform/key_value_store.dart';
import 'package:barterly/src/theme/tokens.dart';
import 'package:material_ui/material_ui.dart';

/// Runtime permissions the app asks for. Each is explained in the app first
/// ([RationaleSheet]), then the system prompt shows the platform string:
/// ios/Runner/Info.plist (NS*UsageDescription) on iOS. Android shows its own
/// fixed wording, so the in-app explanation is the only rationale there.
///
/// Photos need no runtime permission: Android's photo picker and iOS's
/// PHPicker hand over only what the person picks. Keep these texts, the
/// Info.plist strings and docs/store-privacy.md saying the same thing
/// (test/platform/permission_rationale_test.dart checks the plist keys).
enum AppPermission { camera, location, notifications, photos }

@immutable
class Rationale {
  const new({
    required this.icon,
    required this.title,
    required this.body,
    required this.allow,
  });

  final IconData icon;
  final String title;
  final String body;

  /// The button that goes on to the system prompt.
  final String allow;
}

const rationales = <AppPermission, Rationale>{
  AppPermission.camera: Rationale(
    icon: Icons.photo_camera_outlined,
    title: 'Use your camera?',
    body:
        'Take photos or short videos of your work and add them to your '
        'applications and deliverables. Barterly only opens the camera when '
        'you tap to take one.',
    allow: 'Continue',
  ),
  AppPermission.location: Rationale(
    icon: Icons.location_on_outlined,
    title: 'Share where you are for check-in?',
    body:
        'Your host sees how far you are from the property when they check '
        'you in. We read your location once, now, and never in the '
        "background. It's optional: check-in works without it.",
    allow: 'Share location',
  ),
  AppPermission.notifications: Rationale(
    icon: Icons.notifications_outlined,
    title: 'Get notified about your trips?',
    body:
        'Hear straight away when a host replies, sends an offer or confirms '
        'your stay, and get reminders before check-in. No marketing. Change '
        'this any time in Settings.',
    allow: 'Turn on notifications',
  ),
  AppPermission.photos: Rationale(
    icon: Icons.photo_library_outlined,
    title: 'Choose photos and videos',
    body:
        'Pick photos or videos of your work to add to applications. Barterly '
        'only sees the ones you choose.',
    allow: 'Continue',
  ),
};

/// The bottom sheet that explains a permission before the system asks.
/// Pops true for [Rationale.allow], false for "Not now".
class RationaleSheet extends StatelessWidget {
  const new(this.permission, {super.key});

  final AppPermission permission;

  @override
  Widget build(BuildContext context) {
    final r = rationales[permission]!;
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          spacing: BarterlySpace.sm,
          children: [
            Icon(r.icon, size: 32),
            Semantics(
              header: true,
              child: Text(
                r.title,
                style: Theme.of(context).textTheme.titleLarge,
              ),
            ),
            Text(r.body),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: Text(r.allow),
            ),
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Not now'),
            ),
          ],
        ),
      ),
    );
  }
}

/// Shows [RationaleSheet] and returns the answer (false if dismissed).
Future<bool> showRationale(
  BuildContext context,
  AppPermission permission,
) async =>
    await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      builder: (_) => RationaleSheet(permission),
    ) ??
    false;

/// Shows the sheet somewhere the app can reach without a screen's context.
typedef RationalePresenter = Future<bool> Function(AppPermission permission);

/// Decides when to explain before the system prompt:
/// - camera: the first time only (the person just tapped "Take a photo");
/// - notifications: once, and again at most every [askAgainAfter] after "Not
///   now", since the app asks on its own rather than after a tap.
class PermissionPrompts {
  new({required this._store, required this._present, required this._now});

  static const askAgainAfter = Duration(days: 30);
  static String key(AppPermission p) => 'permissions.rationale.v1.${p.name}';

  final KeyValueStore _store;
  final RationalePresenter _present;
  final DateTime Function() _now;

  /// True when the system prompt may follow (or the person already agreed).
  Future<bool> explain(AppPermission permission) async {
    final saved = await _store.readJson(key(permission));
    if (saved?['allowed'] == true) return true;
    if (permission == AppPermission.notifications && saved != null) {
      final at = DateTime.tryParse(saved['at'] as String? ?? '');
      if (at != null && _now().difference(at) < askAgainAfter) return false;
    }
    final allowed = await _present(permission);
    if (allowed || permission == AppPermission.notifications) {
      await _store.writeJson(key(permission), {
        'allowed': allowed,
        'at': _now().toUtc().toIso8601String(),
      });
    }
    return allowed;
  }
}
