import 'package:flutter/foundation.dart';

import '../error/api_error.dart';

/// Phase courante de la synchronisation.
enum SyncPhase {
  /// Rien en cours. Combine a `pendingCount == 0`, cela signifie « a jour ».
  idle,

  /// Envoi ou reception en cours.
  syncing,

  /// Pas de reseau : les ecritures partent en file, rien n'est perdu.
  offline,

  /// Derniere tentative en echec, une reprise est programmee.
  error,
}

/// Etat observable de la synchronisation.
///
/// Expose volontairement de quoi ecrire un test d'integration deterministe
/// (attendre `isSynced` plutot que d'enchainer des `pumpAndSettle` a l'aveugle)
/// et de quoi afficher un bandeau honnete a l'utilisateur.
@immutable
class SyncStatus {
  const SyncStatus({
    this.phase = SyncPhase.idle,
    this.pendingCount = 0,
    this.deadCount = 0,
    this.lastSyncedAt,
    this.lastError,
  });

  final SyncPhase phase;

  /// Nombre d'ecritures locales pas encore acquittees par le serveur.
  final int pendingCount;

  /// Nombre d'operations definitivement rejetees (a montrer a l'utilisateur).
  final int deadCount;

  final DateTime? lastSyncedAt;
  final ApiError? lastError;

  /// Tout est remonte au serveur.
  bool get isSynced => phase == SyncPhase.idle && pendingCount == 0;

  bool get hasPendingWork => pendingCount > 0;
  bool get isOffline => phase == SyncPhase.offline;

  SyncStatus copyWith({
    SyncPhase? phase,
    int? pendingCount,
    int? deadCount,
    DateTime? lastSyncedAt,
    ApiError? lastError,
    bool clearError = false,
  }) {
    return SyncStatus(
      phase: phase ?? this.phase,
      pendingCount: pendingCount ?? this.pendingCount,
      deadCount: deadCount ?? this.deadCount,
      lastSyncedAt: lastSyncedAt ?? this.lastSyncedAt,
      lastError: clearError ? null : (lastError ?? this.lastError),
    );
  }

  @override
  String toString() =>
      'SyncStatus(${phase.name}, pending: $pendingCount, dead: $deadCount)';

  @override
  bool operator ==(Object other) =>
      other is SyncStatus &&
      other.phase == phase &&
      other.pendingCount == pendingCount &&
      other.deadCount == deadCount &&
      other.lastSyncedAt == lastSyncedAt &&
      other.lastError == lastError;

  @override
  int get hashCode =>
      Object.hash(phase, pendingCount, deadCount, lastSyncedAt, lastError);
}
