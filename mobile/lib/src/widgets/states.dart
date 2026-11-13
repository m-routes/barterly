import 'package:barterly/src/theme/tokens.dart';
import 'package:material_ui/material_ui.dart';

/// Loading, empty and error states, so every screen says the same thing the
/// same way. Each is announced to screen readers.

class LoadingView extends StatelessWidget {
  const new({this.label = 'Loading…', super.key});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      liveRegion: true,
      label: label,
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const CircularProgressIndicator(),
            const SizedBox(height: BarterlySpace.lg),
            ExcludeSemantics(
              child: Text(
                label,
                style: const TextStyle(color: BarterlyColors.inkMuted),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _StateCard extends StatelessWidget {
  const new({
    required this.icon,
    required this.title,
    required this.message,
    required this.actions,
    this.isError = false,
  });

  final IconData icon;
  final String title;
  final String message;
  final List<Widget> actions;
  final bool isError;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = isError ? BarterlyColors.danger : BarterlyColors.accent;
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(BarterlySpace.xl),
        child: Semantics(
          liveRegion: isError,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              CircleAvatar(
                radius: 32,
                backgroundColor: isError
                    ? BarterlyColors.dangerSoft
                    : BarterlyColors.accentSoft,
                child: Icon(icon, color: color, size: 32),
              ),
              const SizedBox(height: BarterlySpace.lg),
              Text(
                title,
                style: theme.textTheme.titleLarge,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: BarterlySpace.sm),
              Text(
                message,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: BarterlyColors.inkMuted,
                ),
                textAlign: TextAlign.center,
              ),
              if (actions.isNotEmpty) ...[
                const SizedBox(height: BarterlySpace.xl),
                Wrap(
                  spacing: BarterlySpace.md,
                  runSpacing: BarterlySpace.md,
                  alignment: WrapAlignment.center,
                  children: actions,
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class EmptyState extends StatelessWidget {
  const new({
    required this.icon,
    required this.title,
    required this.message,
    this.action,
    super.key,
  });

  final IconData icon;
  final String title;
  final String message;
  final Widget? action;

  @override
  Widget build(BuildContext context) => _StateCard(
    icon: icon,
    title: title,
    message: message,
    actions: [?action],
  );
}

class ErrorView extends StatelessWidget {
  const new({
    required this.message,
    this.title = 'Something went wrong',
    this.onRetry,
    this.secondary,
    super.key,
  });

  final String title;
  final String message;
  final VoidCallback? onRetry;
  final Widget? secondary;

  @override
  Widget build(BuildContext context) => _StateCard(
    icon: Icons.error_outline,
    title: title,
    message: message,
    isError: true,
    actions: [
      if (onRetry != null)
        FilledButton(onPressed: onRetry, child: const Text('Try again')),
      ?secondary,
    ],
  );
}
