import 'package:flutter/material.dart';

import '../theme/okay_theme.dart';

/// Placeholder slot for the O-Kay mascot. The real artwork is not drawn here: bundle it at
/// [OkayAssets.mascot] and set [MascotSlot.assetAvailable] to true.
class MascotSlot extends StatelessWidget {
  const MascotSlot({super.key, this.size = 40, this.glow = false});

  /// Flip to true once assets/okay/mascot.png is bundled.
  static const bool assetAvailable = false;

  final double size;
  final bool glow;

  @override
  Widget build(BuildContext context) {
    final Widget inner = assetAvailable
        ? Image.asset(OkayAssets.mascot, width: size, height: size)
        : Icon(Icons.smart_toy_outlined, size: size * 0.5, color: OkayColors.textSecondary);
    return Semantics(
      label: 'O-Kay',
      image: true,
      child: Container(
        width: size,
        height: size,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: OkayColors.surfaceElevated,
          border: Border.all(color: OkayColors.chipBorder),
          boxShadow: glow
              ? [
                  BoxShadow(
                    color: OkayColors.gold.withValues(alpha: 0.45),
                    blurRadius: size * 0.6,
                    spreadRadius: size * 0.08,
                  ),
                ]
              : null,
        ),
        child: inner,
      ),
    );
  }
}

/// Assistant screen frame: back arrow, title (optionally with the mascot avatar), body.
class OkayScaffold extends StatelessWidget {
  const OkayScaffold({
    super.key,
    required this.title,
    required this.body,
    this.showMascot = false,
    this.actions,
    this.backgroundColor = OkayColors.background,
    this.floatingActionButton,
  });

  final String title;
  final Widget body;
  final bool showMascot;
  final List<Widget>? actions;
  final Color backgroundColor;
  final Widget? floatingActionButton;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: backgroundColor,
      appBar: AppBar(
        backgroundColor: backgroundColor,
        titleSpacing: (ModalRoute.of(context)?.canPop ?? false) ? 0 : OkaySpacing.gutter,
        title: Row(
          children: [
            if (showMascot) ...[const MascotSlot(size: 32), const SizedBox(width: OkaySpacing.sm)],
            Flexible(child: Text(title, overflow: TextOverflow.ellipsis)),
          ],
        ),
        actions: actions,
      ),
      body: SafeArea(top: false, child: body),
      floatingActionButton: floatingActionButton,
    );
  }
}

class LoadingView extends StatelessWidget {
  const LoadingView({super.key});

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Padding(padding: EdgeInsets.all(OkaySpacing.xxl), child: CircularProgressIndicator()),
    );
  }
}

class ErrorView extends StatelessWidget {
  const ErrorView({super.key, required this.message, this.onRetry});

  final String message;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(OkaySpacing.xl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off_outlined, size: 40, color: OkayColors.textSecondary),
            const SizedBox(height: OkaySpacing.md),
            Text(message, style: OkayText.body, textAlign: TextAlign.center),
            if (onRetry != null) ...[
              const SizedBox(height: OkaySpacing.lg),
              OutlinedButton(onPressed: onRetry, child: const Text('Try again')),
            ],
          ],
        ),
      ),
    );
  }
}

class EmptyView extends StatelessWidget {
  const EmptyView({
    super.key,
    required this.title,
    this.message,
    this.icon = Icons.inbox_outlined,
    this.action,
  });

  final String title;
  final String? message;
  final IconData icon;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(OkaySpacing.xl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 40, color: OkayColors.textSecondary),
            const SizedBox(height: OkaySpacing.md),
            Text(title, style: OkayText.rowTitle, textAlign: TextAlign.center),
            if (message != null) ...[
              const SizedBox(height: OkaySpacing.xs),
              Text(message!, style: OkayText.subtitle, textAlign: TextAlign.center),
            ],
            if (action != null) ...[const SizedBox(height: OkaySpacing.lg), action!],
          ],
        ),
      ),
    );
  }
}
