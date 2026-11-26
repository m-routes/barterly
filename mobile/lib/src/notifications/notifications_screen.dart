import 'dart:async';

import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/discover/gig.dart' show shortDate;
import 'package:barterly/src/notifications/notification_models.dart';
import 'package:barterly/src/providers.dart';
import 'package:barterly/src/router.dart';
import 'package:barterly/src/theme/tokens.dart';
import 'package:barterly/src/widgets/feedback.dart';
import 'package:barterly/src/widgets/states.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

/// The inbox: everything Barterly told you, newest first. Tapping one opens
/// the screen it's about and marks it read.
class NotificationsScreen extends ConsumerStatefulWidget {
  const new({super.key});

  @override
  ConsumerState<NotificationsScreen> createState() =>
      _NotificationsScreenState();
}

class _NotificationsScreenState extends ConsumerState<NotificationsScreen> {
  late Future<List<AppNotification>> _items = _load();

  Future<List<AppNotification>> _load() =>
      ref.read(notificationsRepositoryProvider).inbox();

  void _reload() => setState(() {
    _items = _load();
  });

  Future<void> _open(AppNotification item) async {
    final repository = ref.read(notificationsRepositoryProvider);
    if (!item.read) {
      try {
        await repository.markRead(item.id);
      } on ApiError {
        // Opening it matters more than the read mark.
      }
      ref.invalidate(unreadCountProvider);
    }
    if (!mounted) return;
    if (item.appPath.startsWith('/')) {
      await context.push(item.appPath);
    }
    _reload();
  }

  Future<void> _readAll() async {
    try {
      await ref.read(notificationsRepositoryProvider).markAllRead();
      ref.invalidate(unreadCountProvider);
      _reload();
    } on ApiError catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(error.userMessage)));
      }
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('Notifications'),
      actions: [
        IconButton(
          tooltip: 'Notification settings',
          icon: const Icon(Icons.tune),
          onPressed: () => context.push(Routes.notificationSettings),
        ),
      ],
    ),
    body: FutureBuilder<List<AppNotification>>(
      future: _items,
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          final error = snapshot.error;
          return ErrorView(
            title: "We couldn't load your notifications",
            message: error is ApiError ? error.userMessage : '$error',
            onRetry: _reload,
          );
        }
        final items = snapshot.data;
        if (items == null) return const LoadingView();
        if (items.isEmpty) {
          return const EmptyState(
            icon: Icons.notifications_none,
            title: 'Nothing yet',
            message: 'Offers, agreements and messages show up here.',
          );
        }
        final unread = items.where((n) => !n.read).length;
        return RefreshIndicator(
          onRefresh: () async => _reload(),
          child: ListView(
            children: [
              if (unread > 0)
                Align(
                  alignment: Alignment.centerRight,
                  child: TextButton(
                    onPressed: () => unawaited(_readAll()),
                    child: Text('Mark all $unread read'),
                  ),
                ),
              for (final item in items)
                ListTile(
                  leading: Icon(
                    item.read
                        ? Icons.notifications_none
                        : Icons.notifications_active,
                    color: item.read
                        ? BarterlyColors.inkMuted
                        : BarterlyColors.accent,
                  ),
                  title: Text(
                    item.title,
                    style: TextStyle(
                      fontWeight: item.read ? FontWeight.w400 : FontWeight.w600,
                    ),
                  ),
                  subtitle: Text(
                    '${item.body}\n${shortDate(item.createdAt.toLocal())}',
                  ),
                  isThreeLine: true,
                  trailing: item.urgent
                      ? const Tag(
                          label: 'Urgent',
                          background: BarterlyColors.dangerSoft,
                          foreground: BarterlyColors.danger,
                        )
                      : null,
                  onTap: () => unawaited(_open(item)),
                ),
            ],
          ),
        );
      },
    ),
  );
}

/// Language, quiet hours, and which channels each kind of notification uses.
class NotificationSettingsScreen extends ConsumerStatefulWidget {
  const new({super.key});

  @override
  ConsumerState<NotificationSettingsScreen> createState() =>
      _NotificationSettingsScreenState();
}

class _NotificationSettingsScreenState
    extends ConsumerState<NotificationSettingsScreen> {
  NotificationPrefs? _prefs;
  Object? _error;
  bool _busy = false;
  final _changes = <(String, String), bool>{};

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    try {
      final prefs = await ref
          .read(notificationsRepositoryProvider)
          .preferences();
      if (mounted) setState(() => _prefs = prefs);
    } on ApiError catch (error) {
      if (mounted) setState(() => _error = error);
    }
  }

  void _toggle(EventTypeSetting type, String channel, bool enabled) {
    final prefs = _prefs!;
    setState(() {
      _changes[(type.key, channel)] = enabled;
      _prefs = prefs.copyWith(
        eventTypes: [
          for (final t in prefs.eventTypes)
            if (t.key == type.key) t.with_(channel, enabled: enabled) else t,
        ],
      );
    });
  }

  Future<void> _pickTime({required bool start}) async {
    final prefs = _prefs!;
    final current = start ? prefs.quietStart : prefs.quietEnd;
    final parts = current.split(':');
    final picked = await showTimePicker(
      context: context,
      initialTime: TimeOfDay(
        hour: int.tryParse(parts.first) ?? 22,
        minute: int.tryParse(parts.last) ?? 0,
      ),
    );
    if (picked == null) return;
    final value =
        '${picked.hour.toString().padLeft(2, '0')}:'
        '${picked.minute.toString().padLeft(2, '0')}';
    setState(
      () => _prefs = start
          ? prefs.copyWith(quietStart: value)
          : prefs.copyWith(quietEnd: value),
    );
  }

  Future<void> _save() async {
    setState(() => _busy = true);
    try {
      final saved = await ref
          .read(notificationsRepositoryProvider)
          .savePreferences(
            _prefs!,
            changes: [
              for (final MapEntry(key: (eventType, channel), :value)
                  in _changes.entries)
                (eventType, channel, value),
            ],
          );
      if (!mounted) return;
      setState(() {
        _prefs = saved;
        _changes.clear();
      });
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Saved.')));
    } on ApiError catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(error.userMessage)));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final prefs = _prefs;
    return Scaffold(
      appBar: AppBar(title: const Text('Notification settings')),
      body: switch ((prefs, _error)) {
        (_, final ApiError error) => ErrorView(
          title: "We couldn't load your settings",
          message: error.userMessage,
          onRetry: () {
            setState(() => _error = null);
            unawaited(_load());
          },
        ),
        (null, _) => const LoadingView(),
        (final NotificationPrefs p, _) => ListView(
          padding: const EdgeInsets.all(BarterlySpace.lg),
          children: [
            Text('Language', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: BarterlySpace.sm),
            SegmentedButton<String>(
              segments: const [
                ButtonSegment(value: 'en', label: Text('English')),
                ButtonSegment(value: 'hi', label: Text('हिन्दी')),
              ],
              selected: {p.locale},
              onSelectionChanged: (value) =>
                  setState(() => _prefs = p.copyWith(locale: value.first)),
            ),
            const SizedBox(height: BarterlySpace.lg),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Quiet hours'),
              subtitle: const Text(
                'Hold push, SMS and WhatsApp until they end. Urgent reminders '
                'still come through.',
              ),
              value: p.quietHoursEnabled,
              onChanged: (v) =>
                  setState(() => _prefs = p.copyWith(quietHoursEnabled: v)),
            ),
            if (p.quietHoursEnabled)
              Wrap(
                spacing: BarterlySpace.sm,
                children: [
                  OutlinedButton(
                    onPressed: () => unawaited(_pickTime(start: true)),
                    child: Text('From ${p.quietStart}'),
                  ),
                  OutlinedButton(
                    onPressed: () => unawaited(_pickTime(start: false)),
                    child: Text('Until ${p.quietEnd}'),
                  ),
                ],
              ),
            const SizedBox(height: BarterlySpace.lg),
            Text(
              'What you hear about, and how',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            for (final type in p.eventTypes)
              Padding(
                padding: const EdgeInsets.only(top: BarterlySpace.md),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      type.urgent ? '${type.label} (urgent)' : type.label,
                      style: const TextStyle(fontWeight: FontWeight.w600),
                    ),
                    Wrap(
                      spacing: BarterlySpace.xs,
                      children: [
                        for (final channel in p.channelsAvailable)
                          if (type.channels[channel] case final setting?)
                            FilterChip(
                              label: Text(channelLabels[channel] ?? channel),
                              selected: setting.enabled,
                              onSelected: setting.locked
                                  ? null
                                  : (v) => _toggle(type, channel, v),
                            ),
                      ],
                    ),
                  ],
                ),
              ),
            const SizedBox(height: BarterlySpace.lg),
            FilledButton(
              onPressed: _busy ? null : () => unawaited(_save()),
              child: Text(_busy ? 'Saving…' : 'Save settings'),
            ),
          ],
        ),
      },
    );
  }
}
