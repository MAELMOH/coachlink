import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../l10n/generated/app_localizations.dart';
import '../sync/sync_status.dart';
import '../testing/widget_keys.dart';

/// Bandeau d'etat de synchronisation.
///
/// Regle produit : en salle, l'utilisateur doit pouvoir continuer a cocher ses
/// series sans reseau **et le savoir**. Le bandeau rassure ("vos donnees sont
/// enregistrees sur l'appareil") au lieu d'alarmer : rien n'est perdu, c'est
/// tout l'interet de la file de synchronisation.
class SyncStatusBanner extends ConsumerWidget {
  const SyncStatusBanner({required this.status, super.key});

  final SyncStatus status;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final AppL10n l10n = AppL10n.of(context);
    final ColorScheme scheme = Theme.of(context).colorScheme;

    if (status.isSynced) {
      return const SizedBox.shrink();
    }

    final (IconData icon, String label, Color background, Color foreground) =
        switch (status.phase) {
      SyncPhase.offline => (
          Icons.cloud_off_outlined,
          l10n.syncStatusOffline,
          scheme.surfaceContainerHighest,
          scheme.onSurface,
        ),
      SyncPhase.syncing => (
          Icons.sync,
          l10n.syncStatusSyncing,
          scheme.secondaryContainer,
          scheme.onSecondaryContainer,
        ),
      SyncPhase.error => (
          Icons.error_outline,
          l10n.syncStatusError,
          scheme.errorContainer,
          scheme.onErrorContainer,
        ),
      SyncPhase.idle => (
          Icons.schedule,
          l10n.syncStatusPending(status.pendingCount),
          scheme.surfaceContainerHighest,
          scheme.onSurface,
        ),
    };

    return Semantics(
      liveRegion: true,
      child: Container(
        key: K.syncStatusBanner,
        width: double.infinity,
        color: background,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        child: Row(
          children: <Widget>[
            Icon(icon, size: 18, color: foreground),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                label,
                style: Theme.of(context)
                    .textTheme
                    .bodySmall
                    ?.copyWith(color: foreground),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
