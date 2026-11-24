import 'dart:async';

import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/attendance/attendance_models.dart';
import 'package:barterly/src/attendance/location.dart';
import 'package:barterly/src/attendance/totp.dart';
import 'package:barterly/src/platform/device_security.dart';
import 'package:barterly/src/platform/permission_rationale.dart';
import 'package:barterly/src/providers.dart';
import 'package:barterly/src/theme/tokens.dart';
import 'package:barterly/src/widgets/feedback.dart';
import 'package:barterly/src/widgets/states.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import 'package:material_ui/material_ui.dart';
import 'package:qr_flutter/qr_flutter.dart';

/// The check-in pass: a QR code for the host to scan, and a six-digit code to
/// read out if scanning fails. Both work without signal once the pass is on the
/// phone.
class CheckInPassScreen extends ConsumerStatefulWidget {
  const new({required this.bookingId, super.key});

  final String bookingId;

  @override
  ConsumerState<CheckInPassScreen> createState() => _CheckInPassScreenState();
}

class _CheckInPassScreenState extends ConsumerState<CheckInPassScreen> {
  CheckInPass? _pass;
  String? _error;
  bool _loading = true;
  bool _offline = false;
  Timer? _ticker;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
    // Redraw each second: the code changes every few minutes, with a countdown.
    _ticker = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _ticker?.cancel();
    super.dispose();
  }

  Future<void> _load({bool refresh = false}) async {
    final repo = ref.read(attendanceRepositoryProvider);
    final now = ref.read(clockProvider)();
    final cached = await repo.cachedPass(widget.bookingId);
    if (!mounted) return;
    if (cached != null && !refresh) {
      setState(() {
        _pass = cached;
        _loading = false;
      });
      if (!cached.staleAt(now)) return;
    }
    try {
      final location = await _location();
      final fresh = await repo.fetchPass(widget.bookingId, location: location);
      if (!mounted) return;
      setState(() {
        _pass = fresh;
        _error = null;
        _offline = false;
        _loading = false;
      });
    } on ApiError catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _offline = e.code == 'network_error';
        // Keep showing a cached pass when the network is down.
        _error = _pass != null && _offline ? null : e.userMessage;
      });
    }
  }

  /// The talent's location, if they allow it. Explains why before the system
  /// prompt, asks only once per booking, and accepts "Not now".
  Future<Located?> _location() async {
    final reader = ref.read(locationReaderProvider);
    var access = await reader.access();
    if (access == LocationAccess.notAsked && mounted) {
      final store = ref.read(keyValueStoreProvider);
      final key = 'attendance.location_asked.${widget.bookingId}';
      if (await store.readJson(key) == null && mounted) {
        final share = await showModalBottomSheet<bool>(
          context: context,
          isScrollControlled: true,
          builder: (_) => const RationaleSheet(AppPermission.location),
        );
        await store.writeJson(key, {'asked': true, 'shared': share ?? false});
        if (share ?? false) access = await reader.request();
      }
    }
    return access == LocationAccess.granted ? await reader.current() : null;
  }

  @override
  Widget build(BuildContext context) {
    final now = ref.watch(clockProvider)();
    final pass = _pass;
    return SecureScreen(
      child: Scaffold(
        appBar: AppBar(title: const Text('Check-in pass')),
        body: switch ((pass, _loading, _error)) {
          (_, true, _) => const LoadingView(label: 'Getting your pass…'),
          (null, _, final String error) ||
          (_, _, final String error) => ErrorView(
            title: "We couldn't get your pass",
            message: error,
            onRetry: () => _load(refresh: true),
          ),
          (final CheckInPass p, _, _) => _PassBody(
            pass: p,
            now: now,
            offline: _offline,
            onRefresh: () => _load(refresh: true),
          ),
          _ => const SizedBox.shrink(),
        },
      ),
    );
  }
}

class _PassBody extends StatelessWidget {
  const new({
    required this.pass,
    required this.now,
    required this.offline,
    required this.onRefresh,
  });

  final CheckInPass pass;
  final DateTime now;
  final bool offline;
  final Future<void> Function() onRefresh;

  @override
  Widget build(BuildContext context) {
    final valid = pass.validAt(now);
    final code = codeAt(
      pass.codeSecret,
      now,
      periodSeconds: pass.codePeriodSeconds,
    );
    final left = codeTimeLeft(now, periodSeconds: pass.codePeriodSeconds);
    final until = DateFormat('d MMM, h:mm a').format(pass.validUntil.toLocal());
    return RefreshIndicator(
      onRefresh: onRefresh,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
        children: [
          if (offline)
            const Padding(
              padding: EdgeInsets.only(bottom: BarterlySpace.sm),
              child: Tag(
                label: 'Offline: showing the pass saved on this phone',
                icon: Icons.cloud_off_outlined,
              ),
            ),
          SurfaceCard(
            child: Column(
              spacing: BarterlySpace.md,
              children: [
                Text(
                  'Show this to your host',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                if (valid)
                  Semantics(
                    label: 'Check-in QR code',
                    image: true,
                    child: QrImageView(
                      data: pass.token,
                      size: 240,
                      backgroundColor: BarterlyColors.surface,
                    ),
                  )
                else
                  const Text(
                    "This pass isn't valid right now. Pull down to get a "
                    'fresh one when you have signal.',
                    textAlign: TextAlign.center,
                  ),
                Text(
                  'Valid until $until',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
          ),
          const SizedBox(height: BarterlySpace.md),
          SurfaceCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              spacing: BarterlySpace.sm,
              children: [
                Text(
                  "If the scan doesn't work",
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const Text('Read this code to your host:'),
                Semantics(
                  label: 'Check-in code ${code.split('').join(' ')}',
                  excludeSemantics: true,
                  child: Text(
                    '${code.substring(0, 3)} ${code.substring(3)}',
                    style: Theme.of(context).textTheme.displaySmall?.copyWith(
                      fontFeatures: const [FontFeature.tabularFigures()],
                      letterSpacing: 4,
                    ),
                  ),
                ),
                Text(
                  'New code in ${left.inMinutes}:'
                  '${(left.inSeconds % 60).toString().padLeft(2, '0')}',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
          ),
          const SizedBox(height: BarterlySpace.md),
          const Text(
            'Your location when you opened this pass is shared with your host '
            "to confirm you've arrived. It never stops you checking in.",
          ),
        ],
      ),
    );
  }
}

/// Why the pass asks for location, before the system prompt does.
