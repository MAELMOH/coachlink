import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/router/routes.dart';
import '../../../core/sync/sync_service.dart';
import '../../../core/sync/sync_status.dart';
import '../../../core/testing/widget_keys.dart';
import '../../../core/widgets/sync_status_banner.dart';
import '../../../l10n/generated/app_localizations.dart';
import '../../auth/domain/session.dart';
import '../../auth/presentation/session_controller.dart';

/// Coquille commune aux deux parcours : bandeau d'essai, bandeau de
/// synchronisation, acces a « Mes donnees ».
///
/// Les ecrans metier (dashboard coach, seance du jour) arrivent en 3.3 et 3.4 ;
/// cette coquille existe des le socle pour que le cablage navigation +
/// synchronisation + session soit testable de bout en bout tout de suite.
class HomeShell extends ConsumerWidget {
  const HomeShell({
    required this.title,
    required this.body,
    this.shellKey,
    super.key,
  });

  final String title;
  final Widget body;
  final Key? shellKey;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final AppL10n l10n = AppL10n.of(context);
    final Session session = ref.watch(sessionProvider);

    return Scaffold(
      key: shellKey,
      appBar: AppBar(
        title: Text(title),
        actions: <Widget>[
          if (session.isReadOnly)
            Padding(
              padding: const EdgeInsets.symmetric(
                horizontal: 8,
                vertical: 12,
              ),
              child: Chip(
                key: K.readOnlyBadge,
                label: Text(l10n.readOnlyBadge),
                visualDensity: VisualDensity.compact,
              ),
            ),
          IconButton(
            tooltip: l10n.myDataTitle,
            onPressed: () => context.push(Routes.myData),
            icon: const Icon(Icons.shield_outlined),
          ),
        ],
      ),
      body: Column(
        children: <Widget>[
          const _SyncBanner(),
          _TrialBanner(session: session),
          Expanded(child: body),
        ],
      ),
    );
  }
}

class _SyncBanner extends ConsumerWidget {
  const _SyncBanner();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Le socle n'ouvre la base locale qu'apres authentification : tant que le
    // provider n'est pas surcharge, on n'affiche simplement rien plutot que
    // de faire planter l'ecran.
    try {
      final AsyncValue<SyncStatus> status = ref.watch(syncStatusProvider);
      return status.maybeWhen(
        data: (SyncStatus value) => SyncStatusBanner(status: value),
        orElse: () => const SizedBox.shrink(),
      );
    } on Object {
      return const SizedBox.shrink();
    }
  }
}

class _TrialBanner extends StatelessWidget {
  const _TrialBanner({required this.session});

  final Session session;

  @override
  Widget build(BuildContext context) {
    final AppL10n l10n = AppL10n.of(context);
    final int? days = session.trialDaysRemaining();
    if (days == null || session.isReadOnly) {
      return const SizedBox.shrink();
    }

    final ColorScheme scheme = Theme.of(context).colorScheme;
    return Container(
      key: K.trialBanner,
      width: double.infinity,
      color: scheme.tertiaryContainer,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      child: Text(
        l10n.trialBannerRemaining(days),
        style: Theme.of(context)
            .textTheme
            .bodySmall
            ?.copyWith(color: scheme.onTertiaryContainer),
      ),
    );
  }
}

/// Placeholder du dashboard coach (Phase 3.3).
class CoachHomeScreen extends ConsumerWidget {
  const CoachHomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final AppL10n l10n = AppL10n.of(context);
    return HomeShell(
      shellKey: K.coachDashboard,
      title: l10n.coachDashboardTitle,
      body: _Placeholder(
        icon: Icons.groups_outlined,
        message: l10n.emptyStateNoClients,
        actionLabel: l10n.coachInviteTitle,
        onAction: () => context.push(Routes.coachInvite),
      ),
    );
  }
}

/// Placeholder de la seance du jour (Phase 3.4).
class ClientHomeScreen extends ConsumerWidget {
  const ClientHomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final AppL10n l10n = AppL10n.of(context);
    return HomeShell(
      shellKey: K.clientTodaySession,
      title: l10n.todaySessionTitle,
      body: _Placeholder(
        icon: Icons.fitness_center_outlined,
        message: l10n.noSessionToday,
        actionLabel: l10n.inviteAcceptTitle,
        onAction: () => context.push(Routes.invite),
      ),
    );
  }
}

class _Placeholder extends StatelessWidget {
  const _Placeholder({
    required this.icon,
    required this.message,
    required this.actionLabel,
    required this.onAction,
  });

  final IconData icon;
  final String message;
  final String actionLabel;
  final VoidCallback onAction;

  @override
  Widget build(BuildContext context) {
    return Center(
      key: K.emptyState,
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(
              icon,
              size: 48,
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
            const SizedBox(height: 16),
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: 20),
            OutlinedButton(onPressed: onAction, child: Text(actionLabel)),
          ],
        ),
      ),
    );
  }
}
