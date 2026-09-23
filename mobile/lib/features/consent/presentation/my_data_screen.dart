import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/session/local_data_purge.dart';
import '../../../core/testing/widget_keys.dart';
import '../../../l10n/generated/app_localizations.dart';
import '../../auth/domain/auth_repository.dart';
import '../../auth/domain/session.dart';
import '../../auth/presentation/session_controller.dart';
import '../domain/consent.dart';

/// Ecran « Mes donnees » (ARCHITECTURE.md 5.3).
///
/// Trois droits y sont exercables directement, sans passer par le support :
/// revocation d'un consentement, export (portabilite), suppression du compte.
/// Revoquer `health_data` declenche le parcours de suppression : c'est
/// annonce explicitement avant confirmation, pas decouvert apres coup.
class MyDataScreen extends ConsumerWidget {
  const MyDataScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final AppL10n l10n = AppL10n.of(context);
    final Session session = ref.watch(sessionProvider);

    return Scaffold(
      appBar: AppBar(title: Text(l10n.myDataTitle)),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: <Widget>[
            Text(
              l10n.myDataConsents,
              style: Theme.of(context).textTheme.titleSmall,
            ),
            const SizedBox(height: 8),
            ...ConsentPurpose.values.map(
              (ConsentPurpose purpose) => _ConsentRow(
                purpose: purpose,
                granted: session.consents.isGranted(purpose),
                onRevoke: () => _confirmRevoke(context, ref, purpose),
              ),
            ),
            const Divider(height: 32),
            ListTile(
              key: K.myDataExport,
              leading: const Icon(Icons.download_outlined),
              title: Text(l10n.myDataExport),
              subtitle: Text(l10n.myDataExportHint),
              contentPadding: EdgeInsets.zero,
              onTap: () => _requestExport(context, ref),
            ),
            ListTile(
              key: K.myDataDelete,
              leading: Icon(
                Icons.delete_outline,
                color: Theme.of(context).colorScheme.error,
              ),
              title: Text(l10n.myDataDelete),
              subtitle: Text(l10n.myDataDeleteHint),
              contentPadding: EdgeInsets.zero,
              onTap: () => _confirmDeletion(context, ref),
            ),
            const Divider(height: 32),
            OutlinedButton.icon(
              key: K.logoutButton,
              onPressed: () => _signOut(context, ref),
              icon: const Icon(Icons.logout),
              label: Text(l10n.authLogout),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _requestExport(BuildContext context, WidgetRef ref) async {
    final AppL10n l10n = AppL10n.of(context);
    final ScaffoldMessengerState messenger = ScaffoldMessenger.of(context);
    await ref.read(authRepositoryProvider).requestDataExport();
    messenger.showSnackBar(
      SnackBar(content: Text(l10n.myDataExportHint)),
    );
  }

  Future<void> _confirmRevoke(
    BuildContext context,
    WidgetRef ref,
    ConsentPurpose purpose,
  ) async {
    final AppL10n l10n = AppL10n.of(context);
    final bool confirmed = await _confirm(
      context,
      title: l10n.myDataRevoke,
      // Revoquer un consentement obligatoire rend le service inutilisable et
      // ouvre le parcours de suppression : on le dit avant, pas apres.
      body: purpose.isMandatory
          ? l10n.myDataDeleteHint
          : l10n.consentBlockedBody,
    );
    if (!confirmed) {
      return;
    }
    await ref.read(sessionProvider.notifier).revokeConsent(purpose);
  }

  Future<void> _confirmDeletion(BuildContext context, WidgetRef ref) async {
    final AppL10n l10n = AppL10n.of(context);
    final bool confirmed = await _confirm(
      context,
      title: l10n.myDataDelete,
      body: l10n.myDataDeleteHint,
    );
    if (!confirmed) {
      return;
    }
    await ref.read(authRepositoryProvider).requestAccountDeletion();
  }

  Future<void> _signOut(BuildContext context, WidgetRef ref) async {
    final PurgeReport report =
        await ref.read(sessionProvider.notifier).signOut();
    if (!context.mounted || report.isComplete) {
      return;
    }
    // On n'echoue pas silencieusement sur une purge incomplete : c'est une
    // information de securite qui doit remonter.
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(AppL10n.of(context).errorUnknown)),
    );
  }

  Future<bool> _confirm(
    BuildContext context, {
    required String title,
    required String body,
  }) async {
    final AppL10n l10n = AppL10n.of(context);
    final bool? result = await showDialog<bool>(
      context: context,
      builder: (BuildContext dialogContext) => AlertDialog(
        title: Text(title),
        content: Text(body),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: Text(l10n.commonCancel),
          ),
          FilledButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: Text(l10n.commonContinue),
          ),
        ],
      ),
    );
    return result ?? false;
  }
}

class _ConsentRow extends StatelessWidget {
  const _ConsentRow({
    required this.purpose,
    required this.granted,
    required this.onRevoke,
  });

  final ConsentPurpose purpose;
  final bool granted;
  final VoidCallback onRevoke;

  @override
  Widget build(BuildContext context) {
    final AppL10n l10n = AppL10n.of(context);
    return ListTile(
      contentPadding: EdgeInsets.zero,
      leading: Icon(
        granted ? Icons.check_circle_outline : Icons.radio_button_unchecked,
        color: granted ? Theme.of(context).colorScheme.primary : null,
      ),
      title: Text(_label(l10n, purpose)),
      trailing: granted
          ? TextButton(
              key: K.myDataRevoke(purpose.wireValue),
              onPressed: onRevoke,
              child: Text(l10n.myDataRevoke),
            )
          : null,
    );
  }

  static String _label(AppL10n l10n, ConsentPurpose purpose) {
    switch (purpose) {
      case ConsentPurpose.tos:
        return l10n.consentTos;
      case ConsentPurpose.privacy:
        return l10n.consentPrivacy;
      case ConsentPurpose.healthData:
        return l10n.consentHealthData;
      case ConsentPurpose.progressPhotos:
        return l10n.consentProgressPhotos;
      case ConsentPurpose.marketing:
        return l10n.consentMarketing;
    }
  }
}
