import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/error/api_error.dart';
import '../../../core/network/error_interceptor.dart';
import '../../../core/sync/entity_ownership.dart';
import '../../../core/testing/widget_keys.dart';
import '../../../core/widgets/error_message.dart';
import '../../../l10n/generated/app_localizations.dart';
import 'session_controller.dart';

/// Inscription avec choix du role.
///
/// Le role determine tout le parcours (dashboard multi-clients vs seance du
/// jour) et n'est pas modifiable ensuite : il est donc demande explicitement,
/// jamais deduit.
class SignUpScreen extends ConsumerStatefulWidget {
  const SignUpScreen({super.key});

  @override
  ConsumerState<SignUpScreen> createState() => _SignUpScreenState();
}

class _SignUpScreenState extends ConsumerState<SignUpScreen> {
  final TextEditingController _email = TextEditingController();
  final TextEditingController _password = TextEditingController();
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();

  UserRole? _role;
  bool _submitting = false;
  ApiError? _error;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final UserRole? role = _role;
    if (role == null || !(_formKey.currentState?.validate() ?? false)) {
      return;
    }
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      await ref.read(sessionProvider.notifier).signUp(
            email: _email.text.trim(),
            password: _password.text,
            role: role,
          );
      // Le routeur redirige vers l'ecran de consentement : un compte neuf
      // n'a par definition accorde aucun consentement.
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
      appBar: AppBar(title: Text(l10n.authSignUpTitle)),
      body: SafeArea(
        child: Form(
          key: _formKey,
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: <Widget>[
              Text(
                l10n.authRoleQuestion,
                style: Theme.of(context).textTheme.titleSmall,
              ),
              const SizedBox(height: 8),
              Row(
                children: <Widget>[
                  Expanded(
                    child: _RoleChoice(
                      choiceKey: K.signupRoleCoach,
                      label: l10n.authRoleCoach,
                      icon: Icons.groups_outlined,
                      selected: _role == UserRole.coach,
                      onTap: () => setState(() => _role = UserRole.coach),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: _RoleChoice(
                      choiceKey: K.signupRoleClient,
                      label: l10n.authRoleClient,
                      icon: Icons.fitness_center_outlined,
                      selected: _role == UserRole.client,
                      onTap: () => setState(() => _role = UserRole.client),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 20),
              TextFormField(
                key: K.signupEmailField,
                controller: _email,
                keyboardType: TextInputType.emailAddress,
                autocorrect: false,
                decoration: InputDecoration(labelText: l10n.authEmail),
                validator: (String? value) =>
                    (value == null || !value.contains('@'))
                        ? l10n.errorValidation
                        : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                key: K.signupPasswordField,
                controller: _password,
                obscureText: true,
                decoration: InputDecoration(labelText: l10n.authPassword),
                validator: (String? value) =>
                    (value == null || value.length < 8)
                        ? l10n.errorValidation
                        : null,
              ),
              if (_error != null) ...<Widget>[
                const SizedBox(height: 8),
                ErrorMessage(error: _error!),
              ],
              const SizedBox(height: 20),
              FilledButton(
                key: K.signupSubmit,
                onPressed: (_role == null || _submitting) ? null : _submit,
                child: _submitting
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : Text(l10n.authSignUp),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _RoleChoice extends StatelessWidget {
  const _RoleChoice({
    required this.choiceKey,
    required this.label,
    required this.icon,
    required this.selected,
    required this.onTap,
  });

  final Key choiceKey;
  final String label;
  final IconData icon;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return Semantics(
      selected: selected,
      button: true,
      child: InkWell(
        key: choiceKey,
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 20),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: selected ? scheme.primary : scheme.outlineVariant,
              width: selected ? 2 : 1,
            ),
            color: selected ? scheme.primaryContainer : null,
          ),
          child: Column(
            children: <Widget>[
              Icon(icon, color: selected ? scheme.primary : scheme.onSurface),
              const SizedBox(height: 8),
              Text(label, style: Theme.of(context).textTheme.labelLarge),
            ],
          ),
        ),
      ),
    );
  }
}
