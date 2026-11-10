import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../chat/chat_controller.dart';
import '../core/api_client.dart';
import '../data/models.dart';
import '../data/providers.dart';
import '../theme/okay_theme.dart';
import '../widgets/widgets.dart';

/// Assistant settings: reply language, calendar, alerts, how data is used, clear chat history.
class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  static const _days = [
    'sunday',
    'monday',
    'tuesday',
    'wednesday',
    'thursday',
    'friday',
    'saturday',
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final settings = ref.watch(settingsProvider);
    Future<void> save(AssistantSettings next) async {
      try {
        await ref.read(settingsProvider.notifier).save(next);
      } on ApiException catch (e) {
        if (context.mounted) {
          ScaffoldMessenger.of(context)
              .showSnackBar(SnackBar(content: Text("Couldn't save: ${e.message}")));
        }
      }
    }

    return OkayScaffold(
      title: 'Assistant settings',
      body: AsyncBody(
        value: settings,
        onRetry: () => ref.invalidate(settingsProvider),
        data: (s) => ListView(
          padding: const EdgeInsets.only(bottom: OkaySpacing.xxl),
          children: [
            const _Heading('Language'),
            _Choice(
              options: const [('en', 'English'), ('ne', 'नेपाली'), ('auto', 'Auto')],
              selected: s.language,
              onSelect: (v) => save(s.copyWith(language: v)),
            ),
            const Padding(
              padding: EdgeInsets.symmetric(
                horizontal: OkaySpacing.gutter,
                vertical: OkaySpacing.xs,
              ),
              child: Text(
                'Auto replies in the language you write in, including Romanized Nepali.',
                style: OkayText.caption,
              ),
            ),
            const _Heading('Calendar'),
            _Choice(
              options: const [('AD', 'AD (English)'), ('BS', 'BS (Nepali)')],
              selected: s.calendar,
              onSelect: (v) => save(s.copyWith(calendar: v)),
            ),
            const _Heading('Alerts'),
            _Toggle(
              title: 'Budget alerts',
              subtitle: 'When a budget reaches 80% and 100%',
              value: s.budgetAlerts,
              onChanged: (v) => save(s.copyWith(budgetAlerts: v)),
            ),
            _Toggle(
              title: 'Bill reminders',
              subtitle: '3 days before a bill is due',
              value: s.billAlerts,
              onChanged: (v) => save(s.copyWith(billAlerts: v)),
            ),
            _Toggle(
              title: 'Unusual spending',
              subtitle: 'When a category is at twice its usual level',
              value: s.unusualAlerts,
              onChanged: (v) => save(s.copyWith(unusualAlerts: v)),
            ),
            _Toggle(
              title: 'Weekly summary',
              subtitle: 'A short recap of your week',
              value: s.weeklySummary,
              onChanged: (v) => save(s.copyWith(weeklySummary: v)),
            ),
            if (s.weeklySummary)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: OkaySpacing.gutter),
                child: Row(
                  children: [
                    const Expanded(child: Text('Send it on', style: OkayText.body)),
                    DropdownButton<String>(
                      value: s.weeklySummaryDay,
                      underline: const SizedBox.shrink(),
                      items: [
                        for (final d in _days)
                          DropdownMenuItem(
                            value: d,
                            child: Text('${d[0].toUpperCase()}${d.substring(1)}'),
                          ),
                      ],
                      onChanged: (d) => d == null ? null : save(s.copyWith(weeklySummaryDay: d)),
                    ),
                  ],
                ),
              ),
            const _Heading('Your data'),
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: OkaySpacing.gutter),
              child: OkayCard(child: _DataExplainer()),
            ),
            const SizedBox(height: OkaySpacing.lg),
            MenuRow(
              icon: Icons.delete_outline,
              title: 'Clear chat history',
              subtitle: 'Deletes your messages with O-Kay',
              onTap: () => _clearChat(context, ref),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _clearChat(BuildContext context, WidgetRef ref) async {
    final ok = await showModalBottomSheet<bool>(
      context: context,
      builder: (context) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(OkaySpacing.xl, 0, OkaySpacing.xl, OkaySpacing.xl),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text('Clear chat history?', style: OkayText.sectionTitle),
              const SizedBox(height: OkaySpacing.xs),
              const Text(
                'Your messages with O-Kay are deleted. Your money data is not touched.',
                style: OkayText.subtitle,
              ),
              const SizedBox(height: OkaySpacing.xl),
              FilledButton(
                onPressed: () => Navigator.of(context).pop(true),
                child: const Text('Clear'),
              ),
              const SizedBox(height: OkaySpacing.sm),
              OutlinedButton(
                onPressed: () => Navigator.of(context).pop(false),
                child: const Text('Keep it'),
              ),
            ],
          ),
        ),
      ),
    );
    if (!(ok ?? false)) return;
    try {
      await ref.read(chatControllerProvider.notifier).clear();
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('Chat history cleared')));
      }
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }
}

class _DataExplainer extends StatelessWidget {
  const _DataExplainer();

  static const _points = [
    'O-Kay reads your transactions, budgets, goals and bills to answer your questions.',
    'Every number is worked out by our own code, not guessed by the AI.',
    'Before anything is sent to the AI service, phone numbers, account numbers and reference '
        'IDs are hidden. Notes people write on payments are treated as text, never as orders.',
    'O-Kay never moves money. Payments open the Khalti screen you already know, and you '
        'finish with your MPIN.',
    'O-Kay never asks for your MPIN, OTP or password. If you type one, it is removed.',
    'This prototype uses made-up demo data only.',
  ];

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('How O-Kay uses your data', style: OkayText.rowTitle),
        const SizedBox(height: OkaySpacing.sm),
        for (final p in _points)
          Padding(
            padding: const EdgeInsets.only(bottom: OkaySpacing.sm),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Padding(
                  padding: EdgeInsets.only(top: 7, right: 10),
                  child: CircleAvatar(radius: 3, backgroundColor: OkayColors.gold),
                ),
                Expanded(child: Text(p, style: OkayText.body.copyWith(fontSize: 15))),
              ],
            ),
          ),
      ],
    );
  }
}

class _Heading extends StatelessWidget {
  const _Heading(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.fromLTRB(
      OkaySpacing.gutter,
      OkaySpacing.xl,
      OkaySpacing.gutter,
      OkaySpacing.sm,
    ),
    child: Text(text, style: OkayText.sectionTitle),
  );
}

class _Choice extends StatelessWidget {
  const _Choice({required this.options, required this.selected, required this.onSelect});
  final List<(String, String)> options;
  final String selected;
  final ValueChanged<String> onSelect;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(horizontal: OkaySpacing.gutter),
    child: Wrap(
      spacing: OkaySpacing.sm,
      runSpacing: OkaySpacing.sm,
      children: [
        for (final (value, label) in options)
          PillChip(label: label, selected: selected == value, onTap: () => onSelect(value)),
      ],
    ),
  );
}

class _Toggle extends StatelessWidget {
  const _Toggle({
    required this.title,
    required this.subtitle,
    required this.value,
    required this.onChanged,
  });
  final String title;
  final String subtitle;
  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) => SwitchListTile(
    value: value,
    onChanged: onChanged,
    contentPadding: const EdgeInsets.symmetric(horizontal: OkaySpacing.gutter),
    title: Text(title, style: OkayText.body),
    subtitle: Text(subtitle, style: OkayText.caption),
    activeThumbColor: OkayColors.text,
    activeTrackColor: OkayColors.primary,
  );
}
