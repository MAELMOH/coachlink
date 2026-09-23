import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/error/api_error.dart';
import '../../../core/network/error_interceptor.dart';
import '../../../core/router/routes.dart';
import '../../../core/testing/widget_keys.dart';
import '../../../core/widgets/error_message.dart';
import '../../../l10n/generated/app_localizations.dart';
import 'session_controller.dart';

class SignInScreen extends ConsumerStatefulWidget {
  const SignInScreen({super.key});

  @override
  ConsumerState<SignInScreen> createState() => _SignInScreenState();
}

class _SignInScreenState extends ConsumerState<SignInScreen> {
  final TextEditingController _email = TextEditingController();
  final TextEditingController _password = TextEditingController();
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();

  bool _submitting = false;
  ApiError? _error;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!(_formKey.currentState?.validate() ?? false)) {
      return;
    }
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      await ref.read(sessionProvider.notifier).signIn(
            email: _email.text.trim(),
            password: _password.text,
          );
    } on Object catch (error) {
      if (mounted) {
        setState(() => _error = asApiError(error));
      }
    } finally {
      if (mounted) {
        setState(() => _submitting = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final AppL10n l10n = AppL10n.of(context);

    return Scaffold(
      appBar: AppBar(title: Text(l10n.authSignInTitle)),
      body: SafeArea(
        child: Form(
          key: _formKey,
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: <Widget>[
              TextFormField(
                key: K.loginEmailField,
                controller: _email,
                keyboardType: TextInputType.emailAddress,
                autocorrect: false,
                autofillHints: const <String>[AutofillHints.email],
                decoration: InputDecoration(labelText: l10n.authEmail),
                validator: (String? value) =>
                    (value == null || !value.contains('@'))
                        ? l10n.errorValidation
                        : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                key: K.loginPasswordField,
                controller: _password,
                obscureText: true,
                autofillHints: const <String>[AutofillHints.password],
                decoration: InputDecoration(labelText: l10n.authPassword),
                validator: (String? value) => (value == null || value.isEmpty)
                    ? l10n.errorValidation
                    : null,
                onFieldSubmitted: (_) => _submit(),
              ),
              if (_error != null) ...<Widget>[
                const SizedBox(height: 8),
                ErrorMessage(error: _error!),
              ],
              const SizedBox(height: 20),
              FilledButton(
                key: K.loginSubmit,
                onPressed: _submitting ? null : _submit,
                child: _submitting
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : Text(l10n.authSignIn),
              ),
              const SizedBox(height: 8),
              TextButton(
                onPressed: () => context.push(Routes.signUp),
                child: Text(l10n.authSignUp),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
