import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/router/routes.dart';
import '../../../core/testing/widget_keys.dart';
import '../../../l10n/generated/app_localizations.dart';

/// Fin d'essai : bascule en **lecture seule**, pas en mur bloquant.
///
/// ARCHITECTURE.md 7 : « On ne coupe jamais l'acces a ses propres donnees —
/// c'est aussi une exigence RGPD. » Cet ecran informe et laisse repartir vers
/// le programme et l'historique ; seules les ecritures sont fermees.
class TrialExpiredScreen extends ConsumerWidget {
  const TrialExpiredScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final AppL10n l10n = AppL10n.of(context);

    return Scaffold(
      appBar: AppBar(title: Text(l10n.trialExpiredTitle)),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: <Widget>[
              Icon(
                Icons.lock_clock_outlined,
                size: 48,
                color: Theme.of(context).colorScheme.tertiary,
              ),
              const SizedBox(height: 16),
              Text(
                l10n.trialExpiredBody,
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodyMedium,
              ),
              const SizedBox(height: 24),
              OutlinedButton(
                key: K.readOnlyBadge,
                onPressed: () => context.go(Routes.clientHome),
                child: Text(l10n.readOnlyBadge),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
