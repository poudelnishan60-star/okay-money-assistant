import 'package:flutter/material.dart';

import '../features/ai_assistant/ai_assistant.dart';

/// The public website's frame (not part of the feature):
/// - on screens wider than a phone, the app sits in a centred phone-width column;
/// - every screen carries the "unofficial prototype" label.
class WebFrame extends StatelessWidget {
  const WebFrame({super.key, required this.child});

  final Widget child;

  static const double maxWidth = 440;
  static const String unofficialLabel =
      'Unofficial prototype · not affiliated with Khalti · mock data only';

  @override
  Widget build(BuildContext context) {
    final mq = MediaQuery.of(context);
    final wide = mq.size.width > maxWidth + 40;
    final width = wide ? maxWidth : mq.size.width;

    // Material gives the banner the theme's text style (outside it Flutter falls back to its
    // yellow-underlined debug style).
    Widget app = Material(
      type: MaterialType.transparency,
      child: Column(
        children: [
          _UnofficialBanner(topInset: mq.padding.top),
          Expanded(
            // The banner already covers the status-bar area.
            child: MediaQuery(
              data: mq.copyWith(
                size: Size(width, mq.size.height),
                padding: mq.padding.copyWith(top: 0),
                viewPadding: mq.viewPadding.copyWith(top: 0),
              ),
              child: child,
            ),
          ),
        ],
      ),
    );
    if (!wide) return app;

    app = Center(
      child: Container(
        width: width,
        decoration: const BoxDecoration(
          boxShadow: [BoxShadow(color: Colors.black54, blurRadius: 40)],
        ),
        // Drawn on top so the hairline doesn't eat into the 440 px column.
        foregroundDecoration: const BoxDecoration(
          border: Border.symmetric(vertical: BorderSide(color: OkayColors.divider)),
        ),
        child: ClipRect(child: app),
      ),
    );
    return ColoredBox(color: const Color(0xFF0A0A0A), child: app);
  }
}

class _UnofficialBanner extends StatelessWidget {
  const _UnofficialBanner({required this.topInset});
  final double topInset;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      container: true,
      label: WebFrame.unofficialLabel,
      excludeSemantics: true,
      child: Container(
        width: double.infinity,
        color: OkayColors.surfaceElevated,
        padding: EdgeInsets.fromLTRB(12, topInset + 5, 12, 5),
        child: Text(
          WebFrame.unofficialLabel,
          textAlign: TextAlign.center,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: OkayText.caption.copyWith(color: OkayColors.gold, fontSize: 11),
        ),
      ),
    );
  }
}
