import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/auth/session.dart';
import 'package:barterly/src/profile/talent_profile.dart';
import 'package:barterly/src/profile/validators.dart';
import 'package:barterly/src/providers.dart';
import 'package:barterly/src/theme/tokens.dart';
import 'package:barterly/src/widgets/states.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import 'package:material_ui/material_ui.dart';

/// What the setup form needs before it can show: the saved profile (if any)
/// and the skills to pick from.
typedef SetupData = ({TalentProfile? profile, List<Skill> skills});

final FutureProvider<SetupData> setupDataProvider =
    FutureProvider.autoDispose<SetupData>((ref) async {
      final repo = ref.watch(profileRepositoryProvider);
      final (profile, skills) = await (
        repo.fetchTalentProfile(),
        repo.skills(),
      ).wait;
      return (profile: profile, skills: skills);
    });

/// Create or edit the talent profile. [editing] changes the title and what
/// happens after saving (go back instead of entering the app).
class ProfileSetupScreen extends ConsumerWidget {
  const new({this.editing = false, super.key});

  final bool editing;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final data = ref.watch(setupDataProvider);
    return Scaffold(
      appBar: AppBar(
        title: Text(editing ? 'Edit profile' : 'Set up your profile'),
      ),
      body: SafeArea(
        child: switch (data) {
          AsyncData(:final value) => TalentProfileForm(
            initial: value.profile,
            skills: value.skills,
            editing: editing,
          ),
          AsyncError(:final error) => ErrorView(
            title: "We couldn't load your profile",
            message: error is ApiError
                ? error.userMessage
                : 'Something went wrong. Try again.',
            onRetry: () => ref.invalidate(setupDataProvider),
          ),
          _ => const LoadingView(label: 'Loading your profile…'),
        },
      ),
    );
  }
}

class TalentProfileForm extends ConsumerStatefulWidget {
  const new({
    required this.initial,
    required this.skills,
    this.editing = false,
    super.key,
  });

  final TalentProfile? initial;
  final List<Skill> skills;
  final bool editing;

  @override
  ConsumerState<TalentProfileForm> createState() => _TalentProfileFormState();
}

class _TalentProfileFormState extends ConsumerState<TalentProfileForm> {
  final _form = GlobalKey<FormState>();
  late final TextEditingController _name;
  late final TextEditingController _bio;
  late final TextEditingController _city;
  late final TextEditingController _contactName;
  late final TextEditingController _contactPhone;
  late final TextEditingController _instagram;
  TalentType? _type;
  late Set<String> _skills;
  late Set<String> _languages;
  DateTime? _dob;

  bool _saving = false;
  String? _formError;

  /// Field errors from the API, shown until the field is edited.
  Map<String, String> _serverErrors = const {};

  @override
  void initState() {
    super.initState();
    final p = widget.initial ?? const TalentProfile();
    _name = TextEditingController(text: p.displayName);
    _bio = TextEditingController(text: p.bio);
    _city = TextEditingController(text: p.homeCity);
    _contactName = TextEditingController(text: p.emergencyContactName);
    _contactPhone = TextEditingController(text: p.emergencyContactPhone);
    _instagram = TextEditingController(text: p.instagramHandle);
    _type = p.talentType;
    _skills = {...p.skills};
    _languages = {...p.languages};
    _dob = p.dateOfBirth;
  }

  @override
  void dispose() {
    for (final c in [_name, _bio, _city, _contactName, _contactPhone]) {
      c.dispose();
    }
    _instagram.dispose();
    super.dispose();
  }

  String get _ownPhone {
    final session = ref.read(sessionProvider);
    return session is SignedIn ? session.user.phone : '';
  }

  String? _server(String field) => _serverErrors[field];

  void _clearServer(String field) {
    if (_serverErrors.containsKey(field)) {
      setState(() => _serverErrors = {..._serverErrors}..remove(field));
    }
  }

  Future<void> _pickDob(FormFieldState<DateTime> field) async {
    final latest = latestAdultBirthday();
    final picked = await showDatePicker(
      context: context,
      initialDate: _dob ?? latest,
      firstDate: DateTime(latest.year - 82),
      lastDate: latest,
      initialEntryMode: DatePickerEntryMode.input,
      helpText: 'Date of birth',
      fieldHintText: 'dd/mm/yyyy',
    );
    if (picked == null) return;
    setState(() => _dob = picked);
    field.didChange(picked);
    _clearServer('date_of_birth');
  }

  Future<void> _save() async {
    setState(() {
      _formError = null;
      _serverErrors = const {};
    });
    if (!(_form.currentState?.validate() ?? false)) return;

    final profile = TalentProfile(
      displayName: _name.text.trim(),
      bio: _bio.text.trim(),
      talentType: _type,
      skills: _skills.toList(),
      languages: _languages.toList(),
      homeCity: _city.text.trim(),
      emergencyContactName: _contactName.text.trim(),
      emergencyContactPhone: normalizePhone(_contactPhone.text) ?? '',
      dateOfBirth: _dob,
      instagramHandle: _instagram.text.trim().replaceFirst(RegExp('^@'), ''),
    );

    setState(() => _saving = true);
    try {
      await ref.read(profileRepositoryProvider).saveTalentProfile(profile);
      // The router moves on once /me says the profile is complete.
      await ref.read(sessionProvider.notifier).reload();
      if (widget.editing && mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('Profile saved')));
        Navigator.of(context).maybePop();
      }
    } on ApiError catch (error) {
      if (!mounted) return;
      final fields = error.fieldErrors;
      setState(() {
        _serverErrors = fields;
        _formError = fields.isEmpty || fields.containsKey('root')
            ? fields['root'] ?? error.userMessage
            : 'Some details need fixing. Check the highlighted fields.';
      });
      _form.currentState?.validate();
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    const gap = SizedBox(height: BarterlySpace.lg);
    return Form(
      key: _form,
      autovalidateMode: AutovalidateMode.onUserInteraction,
      // Not a lazy ListView: off-screen fields must stay mounted, or Form
      // can't validate them (or show their errors) when the button is tapped.
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(
          BarterlySpace.xl,
          BarterlySpace.sm,
          BarterlySpace.xl,
          BarterlySpace.xxl,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (!widget.editing) ...[
              Text(
                'Hosts see this before they accept you. '
                'You can change it later.',
                style: theme.textTheme.bodyLarge?.copyWith(
                  color: BarterlyColors.inkMuted,
                ),
              ),
              gap,
            ],
            const _Section('About you'),
            TextFormField(
              controller: _name,
              textCapitalization: TextCapitalization.words,
              autofillHints: const [AutofillHints.name],
              decoration: const InputDecoration(labelText: 'Display name'),
              onChanged: (_) => _clearServer('display_name'),
              validator: (v) =>
                  _server('display_name') ??
                  requiredText(v, 'the name hosts will see', max: 120),
            ),
            gap,
            DropdownButtonFormField<TalentType>(
              initialValue: _type,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'What do you do?'),
              items: [
                for (final t in TalentType.values)
                  DropdownMenuItem(value: t, child: Text(t.label)),
              ],
              onChanged: (value) {
                setState(() => _type = value);
                _clearServer('talent_type');
              },
              validator: (v) =>
                  _server('talent_type') ??
                  (v == null ? 'Choose what you do.' : null),
            ),
            gap,
            TextFormField(
              controller: _bio,
              minLines: 3,
              maxLines: 6,
              maxLength: 2000,
              textCapitalization: TextCapitalization.sentences,
              decoration: const InputDecoration(
                labelText: 'Bio',
                helperText: 'Your work, what you offer, where you’ve been.',
              ),
              onChanged: (_) => _clearServer('bio'),
              validator: (v) =>
                  _server('bio') ?? requiredText(v, 'a short bio', max: 2000),
            ),
            gap,
            TextFormField(
              controller: _city,
              textCapitalization: TextCapitalization.words,
              autofillHints: const [AutofillHints.addressCity],
              decoration: const InputDecoration(labelText: 'Home city'),
              onChanged: (_) => _clearServer('home_city'),
              validator: (v) =>
                  _server('home_city') ??
                  requiredText(v, 'your home city', max: 80),
            ),
            gap,
            FormField<DateTime>(
              initialValue: _dob,
              validator: (v) =>
                  _server('date_of_birth') ?? validateDateOfBirth(v),
              builder: (field) => InkWell(
                onTap: () => _pickDob(field),
                borderRadius: BorderRadius.circular(BarterlyRadius.sm),
                child: InputDecorator(
                  isEmpty: _dob == null,
                  decoration: InputDecoration(
                    labelText: 'Date of birth',
                    helperText: 'You must be 18 or older to join.',
                    errorText: field.errorText,
                    suffixIcon: const Icon(Icons.calendar_today_outlined),
                  ),
                  child: Text(
                    _dob == null
                        ? 'Choose a date'
                        : DateFormat('d MMM y').format(_dob!),
                    style: _dob == null
                        ? const TextStyle(color: BarterlyColors.inkMuted)
                        : null,
                  ),
                ),
              ),
            ),
            const SizedBox(height: BarterlySpace.xl),
            const _Section('Skills'),
            _ChipField(
              label: 'Pick up to $maxSkills',
              options: {for (final s in widget.skills) s.slug: s.name},
              selected: _skills,
              max: maxSkills,
              serverError: _server('skills'),
              emptyError: 'Pick at least one skill.',
              onToggle: (value, {required on}) {
                setState(() => _skills = {..._skills}..toggle(value, on: on));
                _clearServer('skills');
              },
            ),
            const SizedBox(height: BarterlySpace.xl),
            const _Section('Languages'),
            _ChipField(
              label: 'Languages you speak',
              options: languageNames,
              selected: _languages,
              max: maxLanguages,
              serverError: _server('languages'),
              emptyError: 'Pick at least one language.',
              onToggle: (value, {required on}) {
                setState(
                  () => _languages = {..._languages}..toggle(value, on: on),
                );
                _clearServer('languages');
              },
            ),
            const SizedBox(height: BarterlySpace.xl),
            const _Section('Emergency contact'),
            Text(
              'Someone we can call if something goes wrong on a trip. '
              'Hosts never see this.',
              style: theme.textTheme.bodyMedium?.copyWith(
                color: BarterlyColors.inkMuted,
              ),
            ),
            gap,
            TextFormField(
              controller: _contactName,
              textCapitalization: TextCapitalization.words,
              decoration: const InputDecoration(labelText: 'Their name'),
              onChanged: (_) => _clearServer('emergency_contact_name'),
              validator: (v) =>
                  _server('emergency_contact_name') ??
                  requiredText(v, "your emergency contact's name", max: 80),
            ),
            gap,
            TextFormField(
              controller: _contactPhone,
              keyboardType: TextInputType.phone,
              decoration: const InputDecoration(
                labelText: 'Their phone number',
                helperText:
                    'Indian numbers, or include the country code (+44…)',
              ),
              onChanged: (_) => _clearServer('emergency_contact_phone'),
              validator: (v) =>
                  _server('emergency_contact_phone') ??
                  validateEmergencyPhone(v, ownPhone: _ownPhone),
            ),
            const SizedBox(height: BarterlySpace.xl),
            const _Section('Social (optional)'),
            TextFormField(
              controller: _instagram,
              autocorrect: false,
              decoration: const InputDecoration(
                labelText: 'Instagram',
                prefixText: '@',
              ),
              onChanged: (_) => _clearServer('instagram_handle'),
              validator: (v) =>
                  _server('instagram_handle') ?? validateInstagram(v),
            ),
            if (_formError != null) ...[
              gap,
              Semantics(
                liveRegion: true,
                child: Container(
                  padding: const EdgeInsets.all(BarterlySpace.md),
                  decoration: BoxDecoration(
                    color: BarterlyColors.dangerSoft,
                    borderRadius: BorderRadius.circular(BarterlyRadius.sm),
                  ),
                  child: Text(
                    _formError!,
                    style: const TextStyle(color: BarterlyColors.danger),
                  ),
                ),
              ),
            ],
            const SizedBox(height: BarterlySpace.xl),
            FilledButton(
              onPressed: _saving ? null : _save,
              child: Text(
                _saving
                    ? 'Saving…'
                    : widget.editing
                    ? 'Save profile'
                    : 'Finish setup',
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Section extends StatelessWidget {
  const new(this.title);

  final String title;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: BarterlySpace.md),
    child: Semantics(
      header: true,
      child: Text(title, style: Theme.of(context).textTheme.titleMedium),
    ),
  );
}

/// Multi-select chips that take part in the form's validation.
class _ChipField extends StatelessWidget {
  const new({
    required this.label,
    required this.options,
    required this.selected,
    required this.max,
    required this.onToggle,
    required this.emptyError,
    this.serverError,
  });

  final String label;
  final Map<String, String> options;
  final Set<String> selected;
  final int max;

  /// Called with the chip's value; the form updates its own selection, so
  /// quick successive taps can't overwrite each other.
  final void Function(String value, {required bool on}) onToggle;
  final String emptyError;
  final String? serverError;

  @override
  Widget build(BuildContext context) {
    return FormField<Set<String>>(
      initialValue: selected,
      validator: (_) {
        if (serverError != null) return serverError;
        if (selected.isEmpty) return emptyError;
        if (selected.length > max) return 'Pick at most $max.';
        return null;
      },
      builder: (field) {
        final full = selected.length >= max;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '$label · ${selected.length} chosen',
              style: const TextStyle(color: BarterlyColors.inkMuted),
            ),
            const SizedBox(height: BarterlySpace.sm),
            Wrap(
              spacing: BarterlySpace.sm,
              runSpacing: BarterlySpace.xs,
              children: [
                for (final MapEntry(key: value, value: name) in options.entries)
                  FilterChip(
                    label: Text(name),
                    selected: selected.contains(value),
                    onSelected: !selected.contains(value) && full
                        ? null
                        : (on) {
                            onToggle(value, on: on);
                            field.didChange(selected);
                          },
                  ),
              ],
            ),
            if (field.errorText != null)
              Padding(
                padding: const EdgeInsets.only(top: BarterlySpace.sm),
                child: Text(
                  field.errorText!,
                  style: const TextStyle(color: BarterlyColors.danger),
                ),
              ),
          ],
        );
      },
    );
  }
}

extension on Set<String> {
  /// Adds or removes [value]; returns the set for cascades.
  Set<String> toggle(String value, {required bool on}) {
    on ? add(value) : remove(value);
    return this;
  }
}
