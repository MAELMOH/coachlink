import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/error/api_error.dart';
import '../../../core/network/error_interceptor.dart';
import '../../../core/testing/widget_keys.dart';
import '../../../core/widgets/error_message.dart';
import '../../../l10n/generated/app_localizations.dart';
import '../../auth/presentation/session_controller.dart';
import '../domain/consent.dart';

/// Ecran de consentement RGPD **bloquant** (ARCHITECTURE.md 5.2).
///
/// Regles non negociables appliquees ici :
/// - granularite : une case par finalite, jamais un « j'accepte tout » ;
/// - `tos`, `privacy` et `health_data` sont obligatoires : tant qu'ils ne sont
///   pas coches, le bouton de validation est inactif et l'API repondrait de
///   toute facon `403 CONSENT_REQUIRED` ;
/// - `progress_photos` et `marketing` sont **opt-in, decoches par defaut** et
///   visuellement separes des obligatoires ;
/// - aucune case n'est pre-cochee, aucun consentement n'est deduit d'une
///   autre action de l'utilisateur.
class ConsentScreen extends ConsumerStatefulWidget {
  const ConsentScreen({super.key});

  @override
  ConsumerState<ConsentScreen> createState() => _ConsentScreenState();
}

class _ConsentScreenState extends ConsumerState<ConsentScreen> {
  /// Etat initial : toutes les finalites a `false`, y compris les facultatives.
  final Map<ConsentPurpose, bool> _choices = <ConsentPurpose, bool>{
    for (final ConsentPurpose purpose in ConsentPurpose.values) purpose: false,
  };

  bool _submitting = false;
  ApiError? _error;

  bool get _canSubmit =>
      !_submitting &&
      ConsentPurpose.mandatory
          .every((ConsentPurpose p) => _choices[p] ?? false);

  Future<void> _submit() async {
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      await ref
          .read(sessionProvider.notifier)
          .submitConsents(Map<ConsentPurpose, bool>.from(_choices));
      // La redirection est pilotee par le routeur a partir de Session.stage :
      // on ne navigue pas a la main depuis un ecran.
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
    final TextTheme text = Theme.of(context).textTheme;

    return Scaffold(
      appBar: AppBar(title: Text(l10n.consentTitle)),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
          children: <Widget>[
            Text(l10n.consentIntro, style: text.bodyMedium),
            const SizedBox(height: 24),
            _SectionHeader(label: l10n.consentRequiredSection),
            _ConsentTile(
              tileKey: K.consentTosCheckbox,
              title: l10n.consentTos,
              value: _choices[ConsentPurpose.tos] ?? false,
              onChanged: (bool v) =>
                  setState(() => _choices[ConsentPurpose.tos] = v),
            ),
            _ConsentTile(
              tileKey: K.consentPrivacyCheckbox,
              title: l10n.consentPrivacy,
              value: _choices[ConsentPurpose.privacy] ?? false,
              onChanged: (bool v) =>
                  setState(() => _choices[ConsentPurpose.privacy] = v),
            ),
            _ConsentTile(
              tileKey: K.consentHealthCheckbox,
              title: l10n.consentHealthData,
              subtitle: l10n.consentHealthDataHint,
              value: _choices[ConsentPurpose.healthData] ?? false,
              onChanged: (bool v) =>
                  setState(() => _choices[ConsentPurpose.healthData] = v),
            ),
            const SizedBox(height: 24),
            _SectionHeader(label: l10n.consentOptionalSection),
            _ConsentTile(
              tileKey: K.consentPhotosCheckbox,
              title: l10n.consentProgressPhotos,
              subtitle: l10n.consentProgressPhotosHint,
              value: _choices[ConsentPurpose.progressPhotos] ?? false,
              onChanged: (bool v) =>
                  setState(() => _choices[ConsentPurpose.progressPhotos] = v),
            ),
            _ConsentTile(
              tileKey: K.consentMarketingCheckbox,
              title: l10n.consentMarketing,
              value: _choices[ConsentPurpose.marketing] ?? false,
              onChanged: (bool v) =>
                  setState(() => _choices[ConsentPurpose.marketing] = v),
            ),
            if (_error != null) ...<Widget>[
              const SizedBox(height: 16),
              ErrorMessage(error: _error!),
            ],
            const SizedBox(height: 24),
            FilledButton(
              key: K.consentSubmit,
              onPressed: _canSubmit ? _submit : null,
              child: _submitting
                  ? const SizedBox(
                      height: 20,
                      width: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : Text(l10n.consentSubmit),
            ),
          ],
        ),
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Text(
        label.toUpperCase(),
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
              letterSpacing: 1.1,
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
      ),
    );
  }
}

class _ConsentTile extends StatelessWidget {
  const _ConsentTile({
    required this.tileKey,
    required this.title,
    required this.value,
    required this.onChanged,
    this.subtitle,
  });

  final Key tileKey;
  final String title;
  final String? subtitle;
  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    return CheckboxListTile(
      key: tileKey,
      value: value,
      onChanged: (bool? v) => onChanged(v ?? false),
      controlAffinity: ListTileControlAffinity.leading,
      contentPadding: EdgeInsets.zero,
      title: Text(title, style: Theme.of(context).textTheme.bodyMedium),
      subtitle: subtitle == null
          ? null
          : Text(subtitle!, style: Theme.of(context).textTheme.bodySmall),
    );
  }
}
