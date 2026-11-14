import 'dart:async';

import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/providers.dart';
import 'package:barterly/src/shell/tabs.dart' show myProfileProvider;
import 'package:barterly/src/theme/tokens.dart';
import 'package:barterly/src/verification/verification_repository.dart';
import 'package:barterly/src/widgets/feedback.dart';
import 'package:barterly/src/widgets/states.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

final FutureProvider<MyVerification> myVerificationProvider =
    FutureProvider.autoDispose<MyVerification>(
      (ref) => ref.watch(verificationRepositoryProvider).me(),
    );

const Map<String, String> _checkHelp = {
  VerificationRepository.idCheck:
      'A government ID and a selfie, checked by our verification partner. '
      'Many gigs need this.',
  VerificationRepository.socialCheck:
      'Link your Instagram so hosts can trust your audience numbers.',
  'certificate': 'Course or skill certificates (optional).',
  'reference': 'Someone who can vouch for you (optional).',
};

/// Verification status, badges and the checks the talent can start.
class VerificationScreen extends ConsumerStatefulWidget {
  const new({super.key});

  @override
  ConsumerState<VerificationScreen> createState() => _VerificationScreenState();
}

class _VerificationScreenState extends ConsumerState<VerificationScreen> {
  late final AppLifecycleListener _lifecycle;

  @override
  void initState() {
    super.initState();
    // Back from the provider's ID page: show the new status.
    _lifecycle = AppLifecycleListener(
      onResume: () => ref.invalidate(myVerificationProvider),
    );
  }

  @override
  void dispose() {
    _lifecycle.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final data = ref.watch(myVerificationProvider);
    Future<void> refresh() => ref
        .refresh(myVerificationProvider.future)
        .then((_) {}, onError: (_) {});
    return Scaffold(
      appBar: AppBar(title: const Text('Verification')),
      body: RefreshIndicator(
        onRefresh: refresh,
        child: switch (data) {
          AsyncData(:final value) => _Body(me: value),
          AsyncError(:final error) => CustomScrollView(
            physics: const AlwaysScrollableScrollPhysics(),
            slivers: [
              SliverFillRemaining(
                hasScrollBody: false,
                child: ErrorView(
                  title: "We couldn't load your verification",
                  message: error is ApiError
                      ? error.userMessage
                      : 'Something went wrong. Try again.',
                  onRetry: () => ref.invalidate(myVerificationProvider),
                ),
              ),
            ],
          ),
          _ => const SkeletonList(
            label: 'Loading your verification',
            count: 4,
            itemBuilder: _skeleton,
          ),
        },
      ),
    );
  }

  static Widget _skeleton(BuildContext context) => const SurfaceCard(
    child: Row(
      spacing: 12,
      children: [
        SkeletonBox(width: 40, height: 40, radius: 20),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            spacing: 8,
            children: [SkeletonBox(width: 180), SkeletonBox(width: 240)],
          ),
        ),
      ],
    ),
  );
}

class _Body extends ConsumerWidget {
  const new({required this.me});

  final MyVerification me;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
      children: [
        SurfaceCard(
          color: me.trustedMember
              ? BarterlyColors.accentSoft
              : BarterlyColors.surface,
          child: Row(
            spacing: 12,
            children: [
              Icon(
                me.trustedMember
                    ? Icons.verified
                    : Icons.verified_user_outlined,
                color: BarterlyColors.accent,
                size: 32,
              ),
              Expanded(
                child: Text(
                  me.trustedMember
                      ? "You're a trusted member. Hosts see your badge on "
                            'every application.'
                      : 'Finish the required checks to become a trusted '
                            'member. Hosts pick verified talent first.',
                  style: theme.textTheme.bodyMedium,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 20),
        Semantics(
          header: true,
          child: Text('Your badges', style: theme.textTheme.titleMedium),
        ),
        const SizedBox(height: 8),
        if (me.badges.isEmpty)
          const Text(
            'No badges yet. Each check you pass adds one.',
            style: TextStyle(color: BarterlyColors.inkMuted),
          )
        else
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              for (final b in BadgeKind.values)
                if (me.badges.contains(b))
                  Tag(
                    label: b.label,
                    icon: Icons.check,
                    background: BarterlyColors.accentSoft,
                    foreground: BarterlyColors.onAccentSoft,
                  ),
            ],
          ),
        const SizedBox(height: 20),
        Semantics(
          header: true,
          child: Text('Checks', style: theme.textTheme.titleMedium),
        ),
        const SizedBox(height: 8),
        for (final check in me.checks) _CheckCard(check: check),
      ],
    );
  }
}

class _CheckCard extends ConsumerWidget {
  const new({required this.check});

  final CheckSummary check;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final status = check.status;
    final reason = check.latest?.reason ?? '';
    final Widget? action = switch (check.checkType) {
      VerificationRepository.idCheck when status.canStart => FilledButton(
        onPressed: () => unawaited(startIdCheck(context, ref)),
        child: Text(
          status == CaseStatus.notStarted ? 'Verify my ID' : 'Try again',
        ),
      ),
      VerificationRepository.socialCheck when !status.pending => OutlinedButton(
        onPressed: () => showModalBottomSheet<void>(
          context: context,
          isScrollControlled: true,
          showDragHandle: true,
          useSafeArea: true,
          builder: (_) => SocialLinkSheet(check: check),
        ),
        child: Text(
          status == CaseStatus.approved ? 'Change account' : 'Link Instagram',
        ),
      ),
      _ => null,
    };
    final bioCode = check.latest?.details['bio_code'];
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: SurfaceCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          spacing: 8,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    check.label,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                _StatusTag(status: status),
              ],
            ),
            Text(
              [
                _checkHelp[check.checkType] ?? '',
                if (check.required) 'Needed for the trusted member badge.',
              ].where((s) => s.isNotEmpty).join(' '),
              style: const TextStyle(color: BarterlyColors.inkMuted),
            ),
            if (reason.isNotEmpty &&
                (status == CaseStatus.rejected ||
                    status == CaseStatus.changesRequested))
              Text(
                reason,
                style: const TextStyle(color: BarterlyColors.danger),
              ),
            if (status.pending &&
                check.checkType == VerificationRepository.socialCheck &&
                bioCode is String)
              BioCodeNote(code: bioCode),
            if (status.pending &&
                check.checkType == VerificationRepository.idCheck)
              const Text(
                "We'll update this when our partner finishes the check. "
                'Pull down to refresh.',
              ),
            if (action != null)
              Align(alignment: Alignment.centerRight, child: action),
          ],
        ),
      ),
    );
  }
}

class _StatusTag extends StatelessWidget {
  const new({required this.status});

  final CaseStatus status;

  @override
  Widget build(BuildContext context) {
    final (bg, fg, icon) = switch (status) {
      CaseStatus.approved => (
        BarterlyColors.accentSoft,
        BarterlyColors.onAccentSoft,
        Icons.check,
      ),
      CaseStatus.rejected ||
      CaseStatus.changesRequested ||
      CaseStatus.expired => (
        BarterlyColors.dangerSoft,
        BarterlyColors.danger,
        Icons.error_outline,
      ),
      CaseStatus.submitted || CaseStatus.inReview => (
        const Color(0xFFFBE9CF),
        const Color(0xFF6B3F05),
        Icons.hourglass_empty,
      ),
      CaseStatus.notStarted => (
        BarterlyColors.surfaceSunken,
        BarterlyColors.inkMuted,
        null,
      ),
    };
    return Tag(label: status.label, background: bg, foreground: fg, icon: icon);
  }
}

/// Picks an ID type, starts the check and opens the provider's hosted ID and
/// selfie page in the in-app browser.
Future<void> startIdCheck(BuildContext context, WidgetRef ref) async {
  final document = await showModalBottomSheet<IdDocument>(
    context: context,
    showDragHandle: true,
    isScrollControlled: true,
    useSafeArea: true,
    builder: (context) => SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              spacing: 6,
              children: [
                Text(
                  'Which ID will you use?',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const Text(
                  "You'll photograph it and take a selfie on our verification "
                  "partner's secure page. Barterly never stores your ID "
                  'images, only the result and the last four characters.',
                  style: TextStyle(color: BarterlyColors.inkMuted),
                ),
              ],
            ),
          ),
          for (final d in IdDocument.values)
            ListTile(
              leading: const Icon(Icons.badge_outlined),
              title: Text(d.label),
              onTap: () => Navigator.pop(context, d),
            ),
        ],
      ),
    ),
  );
  if (document == null || !context.mounted) return;
  final messenger = ScaffoldMessenger.of(context);
  try {
    final session = await ref
        .read(verificationRepositoryProvider)
        .startIdCheck(document);
    final opened = await ref
        .read(urlOpenerProvider)
        .openInApp(session.redirectUrl);
    if (!opened) {
      messenger.showSnackBar(
        const SnackBar(
          content: Text("We couldn't open the verification page. Try again."),
        ),
      );
    }
  } on ApiError catch (error) {
    messenger.showSnackBar(SnackBar(content: Text(error.userMessage)));
  } finally {
    ref.invalidate(myVerificationProvider);
  }
}

class BioCodeNote extends StatelessWidget {
  const new({required this.code, super.key});

  final String code;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(12),
    decoration: BoxDecoration(
      color: BarterlyColors.accentSoft,
      borderRadius: BorderRadius.circular(14),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      spacing: 8,
      children: [
        const Text(
          'Add this code to your Instagram bio until the check is done:',
          style: TextStyle(color: BarterlyColors.onAccentSoft),
        ),
        Row(
          children: [
            Expanded(
              child: SelectableText(
                code,
                style: const TextStyle(
                  fontWeight: FontWeight.w700,
                  fontSize: 18,
                  letterSpacing: 1,
                  color: BarterlyColors.onAccentSoft,
                ),
              ),
            ),
            IconButton(
              tooltip: 'Copy code',
              icon: const Icon(Icons.copy),
              onPressed: () async {
                await Clipboard.setData(ClipboardData(text: code));
                if (!context.mounted) return;
                ScaffoldMessenger.of(
                  context,
                ).showSnackBar(const SnackBar(content: Text('Code copied.')));
              },
            ),
          ],
        ),
      ],
    ),
  );
}

/// Save the Instagram handle on the profile, then submit it for checking.
class SocialLinkSheet extends ConsumerStatefulWidget {
  const new({required this.check, super.key});

  final CheckSummary check;

  @override
  ConsumerState<SocialLinkSheet> createState() => _SocialLinkSheetState();
}

class _SocialLinkSheetState extends ConsumerState<SocialLinkSheet> {
  final _form = GlobalKey<FormState>();
  final _handle = TextEditingController();
  bool _loadedHandle = false;
  bool _busy = false;
  String? _error;
  String? _code;

  @override
  void dispose() {
    _handle.dispose();
    super.dispose();
  }

  static String? validateHandle(String? value) {
    final handle = (value ?? '').trim().replaceFirst('@', '');
    if (handle.isEmpty) return 'Enter your Instagram username.';
    if (!RegExp(r'^[A-Za-z0-9._]{1,30}$').hasMatch(handle)) {
      return 'Use letters, numbers, dots and underscores only.';
    }
    return null;
  }

  Future<void> _submit() async {
    if (!_form.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final handle = _handle.text.trim().replaceFirst('@', '');
      await ref.read(profileRepositoryProvider).saveInstagramHandle(handle);
      ref.invalidate(myProfileProvider);
      final result = await ref
          .read(verificationRepositoryProvider)
          .submitSocial();
      ref.invalidate(myVerificationProvider);
      setState(() => _code = result.details['bio_code'] as String?);
    } on ApiError catch (error) {
      setState(
        () => _error = error.isValidation && error.fieldErrors.isNotEmpty
            ? error.fieldErrors.values.first
            : error.userMessage,
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final profile = ref.watch(myProfileProvider);
    if (!_loadedHandle && profile.hasValue) {
      _loadedHandle = true;
      _handle.text = profile.value?.instagramHandle ?? '';
    }
    final theme = Theme.of(context);
    return Padding(
      padding: EdgeInsets.fromLTRB(
        20,
        0,
        20,
        20 + MediaQuery.viewInsetsOf(context).bottom,
      ),
      child: Form(
        key: _form,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          spacing: 12,
          children: [
            Text('Link your Instagram', style: theme.textTheme.titleLarge),
            if (_code case final code?) ...[
              const Text(
                'Submitted. Our trust team checks your account within a '
                'couple of days.',
              ),
              BioCodeNote(code: code),
              FilledButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('Done'),
              ),
            ] else ...[
              const Text(
                "We'll give you a short code to put in your bio, so we know "
                'the account is yours. Your follower count is shared with '
                'hosts you apply to.',
                style: TextStyle(color: BarterlyColors.inkMuted),
              ),
              TextFormField(
                controller: _handle,
                enabled: !_busy,
                autocorrect: false,
                decoration: const InputDecoration(
                  labelText: 'Instagram username',
                  prefixText: '@',
                ),
                validator: validateHandle,
              ),
              if (_error case final error?)
                Text(
                  error,
                  style: const TextStyle(color: BarterlyColors.danger),
                ),
              FilledButton(
                onPressed: _busy ? null : _submit,
                child: Text(_busy ? 'Submitting…' : 'Submit for checking'),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
