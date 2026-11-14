import 'dart:async';

import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/auth/phone_auth.dart';
import 'package:barterly/src/auth/session.dart';
import 'package:barterly/src/profile/validators.dart';
import 'package:barterly/src/providers.dart';
import 'package:barterly/src/theme/tokens.dart';
import 'package:barterly/src/widgets/brand.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

/// Phone number → SMS code → API session. Navigation happens in the router
/// once the session changes.
class LoginScreen extends ConsumerStatefulWidget {
  const new({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  static const resendSeconds = 30;

  final _phoneForm = GlobalKey<FormState>();
  final _codeForm = GlobalKey<FormState>();
  final _phone = TextEditingController();
  final _code = TextEditingController();

  String? _sentTo;
  CodeSent? _pending;
  bool _busy = false;
  String? _error;
  String? _codeError;
  int _resendIn = 0;
  Timer? _timer;

  @override
  void dispose() {
    _timer?.cancel();
    _phone.dispose();
    _code.dispose();
    super.dispose();
  }

  void _startCountdown() {
    _timer?.cancel();
    setState(() => _resendIn = resendSeconds);
    _timer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted || _resendIn <= 1) {
        timer.cancel();
        if (mounted) setState(() => _resendIn = 0);
        return;
      }
      setState(() => _resendIn -= 1);
    });
  }

  Future<void> _sendCode() async {
    if (!(_phoneForm.currentState?.validate() ?? false) && _sentTo == null) {
      return;
    }
    final phone = _sentTo ?? normalizeIndianMobile(_phone.text)!;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final result = await ref.read(phoneAuthProvider).sendCode(phone);
      switch (result) {
        case AutoVerified(:final idToken):
          await _exchange(idToken);
        case final CodeSent sent:
          setState(() {
            _sentTo = phone;
            _pending = sent;
            _code.clear();
            _codeError = null;
          });
          _startCountdown();
      }
    } on PhoneAuthException catch (error) {
      setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _verify() async {
    final pending = _pending;
    if (pending == null || !(_codeForm.currentState?.validate() ?? false)) {
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
      _codeError = null;
    });
    try {
      await _exchange(await pending.confirm(_code.text.trim()));
    } on PhoneAuthException catch (error) {
      setState(() => _codeError = error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _exchange(String idToken) async {
    try {
      final user = await ref.read(authRepositoryProvider).exchange(idToken);
      unawaited(ref.read(phoneAuthProvider).signOut());
      ref.read(sessionProvider.notifier).signedIn(user);
    } on ApiError catch (error) {
      if (mounted) setState(() => _error = error.userMessage);
    }
  }

  void _changeNumber() => setState(() {
    _pending = null;
    _sentTo = null;
    _error = null;
    _timer?.cancel();
    _resendIn = 0;
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const BrandMark()),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(BarterlySpace.xl),
          children: _pending == null ? _phoneStep(theme) : _codeStep(theme),
        ),
      ),
    );
  }

  List<Widget> _phoneStep(ThemeData theme) => [
    Text('Sign in to Barterly', style: theme.textTheme.headlineMedium),
    const SizedBox(height: BarterlySpace.sm),
    Text(
      "We'll text you a code. New here? The same steps create your account.",
      style: theme.textTheme.bodyLarge?.copyWith(
        color: BarterlyColors.inkMuted,
      ),
    ),
    const SizedBox(height: BarterlySpace.xl),
    Form(
      key: _phoneForm,
      child: TextFormField(
        controller: _phone,
        autofocus: true,
        keyboardType: TextInputType.phone,
        autofillHints: const [AutofillHints.telephoneNumberNational],
        textInputAction: TextInputAction.done,
        onFieldSubmitted: (_) => _busy ? null : _sendCode(),
        decoration: const InputDecoration(
          labelText: 'Mobile number',
          prefixText: '+91 ',
          helperText: 'Indian numbers only for now',
        ),
        validator: validateMobileForSignIn,
      ),
    ),
    _ErrorText(_error),
    const SizedBox(height: BarterlySpace.xl),
    FilledButton(
      onPressed: _busy ? null : _sendCode,
      child: _busy ? const _ButtonSpinner() : const Text('Send code'),
    ),
  ];

  List<Widget> _codeStep(ThemeData theme) => [
    Text('Enter your code', style: theme.textTheme.headlineMedium),
    const SizedBox(height: BarterlySpace.sm),
    Text(
      'We sent a 6-digit code to $_sentTo.',
      style: theme.textTheme.bodyLarge?.copyWith(
        color: BarterlyColors.inkMuted,
      ),
    ),
    const SizedBox(height: BarterlySpace.xl),
    Form(
      key: _codeForm,
      child: TextFormField(
        controller: _code,
        autofocus: true,
        keyboardType: TextInputType.number,
        autofillHints: const [AutofillHints.oneTimeCode],
        inputFormatters: [
          FilteringTextInputFormatter.digitsOnly,
          LengthLimitingTextInputFormatter(6),
        ],
        onFieldSubmitted: (_) => _busy ? null : _verify(),
        decoration: InputDecoration(labelText: 'Code', errorText: _codeError),
        validator: validateOtp,
      ),
    ),
    _ErrorText(_error),
    const SizedBox(height: BarterlySpace.xl),
    FilledButton(
      onPressed: _busy ? null : _verify,
      child: _busy ? const _ButtonSpinner() : const Text('Verify and continue'),
    ),
    const SizedBox(height: BarterlySpace.md),
    Wrap(
      alignment: WrapAlignment.spaceBetween,
      children: [
        TextButton(
          onPressed: _busy ? null : _changeNumber,
          child: const Text('Change number'),
        ),
        TextButton(
          onPressed: _busy || _resendIn > 0 ? null : _sendCode,
          child: Text(
            _resendIn > 0 ? 'Resend code in ${_resendIn}s' : 'Resend code',
          ),
        ),
      ],
    ),
  ];
}

class _ErrorText extends StatelessWidget {
  const new(this.message);

  final String? message;

  @override
  Widget build(BuildContext context) {
    final text = message;
    if (text == null) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: BarterlySpace.lg),
      child: Semantics(
        liveRegion: true,
        child: Container(
          padding: const EdgeInsets.all(BarterlySpace.md),
          decoration: BoxDecoration(
            color: BarterlyColors.dangerSoft,
            borderRadius: BorderRadius.circular(BarterlyRadius.sm),
          ),
          child: Text(
            text,
            style: const TextStyle(color: BarterlyColors.danger),
          ),
        ),
      ),
    );
  }
}

class _ButtonSpinner extends StatelessWidget {
  const new();

  @override
  Widget build(BuildContext context) => const SizedBox.square(
    dimension: 20,
    child: CircularProgressIndicator(
      strokeWidth: 2.5,
      color: BarterlyColors.onAccent,
      semanticsLabel: 'Working',
    ),
  );
}
