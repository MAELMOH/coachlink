import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/router/pending_invitation.dart';
import '../../../core/testing/widget_keys.dart';
import '../../../l10n/generated/app_localizations.dart';

/// Acceptation d'une invitation coach.
///
/// Deux chemins d'entree, par conception :
/// 1. **Deep link** `https://<host>/invite/<code>` : le code est pre-rempli.
/// 2. **Saisie manuelle** du code a 8 caracteres : c'est le repli assume au
///    *deferred deep linking* (lien -> store -> premier lancement). Un SDK
///    d'attribution tiers reglerait le cas 1 sans installation prealable, mais
///    a ete ecarte par le Tech Lead pour ses implications RGPD. La saisie
///    manuelle reste donc toujours visible, jamais cachee derriere un echec.
class InviteScreen extends ConsumerStatefulWidget {
  const InviteScreen({this.code, super.key});

  final String? code;

  @override
  ConsumerState<InviteScreen> createState() => _InviteScreenState();
}

class _InviteScreenState extends ConsumerState<InviteScreen> {
  late final TextEditingController _controller = TextEditingController(
    text: widget.code ?? ref.read(pendingInvitationProvider) ?? '',
  );

  String? _validationError;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _submit() {
    final AppL10n l10n = AppL10n.of(context);
    final String code = PendingInvitation.normalize(_controller.text);
    if (!PendingInvitation.isValidCode(code)) {
      setState(() => _validationError = l10n.errorValidation);
      return;
    }
    setState(() => _validationError = null);
    ref.read(pendingInvitationProvider.notifier).capture(code);
    // L'acceptation reelle (`POST /invitations/{code}/accept`) arrive avec la
    // Phase 3.3 : elle depend du contrat d'API cote `back`.
  }

  @override
  Widget build(BuildContext context) {
    final AppL10n l10n = AppL10n.of(context);

    return Scaffold(
      appBar: AppBar(title: Text(l10n.inviteAcceptTitle)),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: <Widget>[
            TextField(
              key: K.inviteAcceptCodeField,
              controller: _controller,
              textCapitalization: TextCapitalization.characters,
              autocorrect: false,
              maxLength: PendingInvitation.codeLength,
              inputFormatters: <TextInputFormatter>[
                UpperCaseTextFormatter(),
                FilteringTextInputFormatter.allow(RegExp('[A-Za-z0-9]')),
              ],
              decoration: InputDecoration(
                labelText: l10n.inviteAcceptCodeLabel,
                errorText: _validationError,
              ),
              onSubmitted: (_) => _submit(),
            ),
            const SizedBox(height: 16),
            FilledButton(
              key: K.inviteAcceptSubmit,
              onPressed: _submit,
              child: Text(l10n.inviteAcceptSubmit),
            ),
          ],
        ),
      ),
    );
  }
}

/// Force la saisie en majuscules : les codes d'invitation sont generes en
/// majuscules, et l'utilisateur recopie souvent depuis un SMS en minuscules.
class UpperCaseTextFormatter extends TextInputFormatter {
  const UpperCaseTextFormatter();

  @override
  TextEditingValue formatEditUpdate(
    TextEditingValue oldValue,
    TextEditingValue newValue,
  ) {
    return newValue.copyWith(text: newValue.text.toUpperCase());
  }
}
