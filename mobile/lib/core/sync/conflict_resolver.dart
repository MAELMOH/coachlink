import 'package:collection/collection.dart';

import 'entity_ownership.dart';

/// Issue d'une resolution de conflit.
enum ConflictResolution {
  /// La version serveur ecrase le local (l'utilisateur n'ecrit pas cette entite).
  remoteWins,

  /// La version locale gagne (l'utilisateur est le proprietaire d'ecriture).
  localWins,

  /// Fusion champ par champ (entites partagees uniquement).
  merged,

  /// Rien a resoudre : pas de modification locale en attente.
  noConflict,
}

class MergeOutcome {
  const MergeOutcome({required this.resolution, required this.fields});

  final ConflictResolution resolution;
  final Map<String, Object?> fields;

  @override
  String toString() => 'MergeOutcome($resolution, $fields)';
}

/// Resolution des conflits de `GET /sync` cote mobile.
///
/// ## Les regles, dans l'ordre d'application
///
/// 1. **`set_log` : le client fait toujours foi.** Non negociable
///    (ARCHITECTURE.md 8). Une serie cochee a la salle n'est jamais ecrasee
///    par le serveur, meme si l'horodatage serveur est plus recent.
/// 2. **Proprietaire d'ecriture unique.** Si l'utilisateur n'ecrit pas
///    l'entite (ex. un client qui recoit un `program`), la version serveur
///    gagne systematiquement : il n'a rien a defendre.
/// 3. **Merge a 3 voies** pour les entites partagees. `/sync` versionne par
///    enregistrement et non par champ : on ne peut donc appliquer un
///    « last-write-wins par champ » qu'aux champs que l'utilisateur a
///    reellement modifies localement, ce qui se deduit de la comparaison avec
///    le `baseSnapshot` (derniere version connue du serveur).
class ConflictResolver {
  const ConflictResolver(this.role);

  final UserRole role;

  MergeOutcome resolve({
    required SyncEntityType entity,
    required Map<String, Object?> base,
    required Map<String, Object?> local,
    required Map<String, Object?> remote,
    required bool hasLocalChanges,
  }) {
    if (!hasLocalChanges) {
      return MergeOutcome(
        resolution: ConflictResolution.noConflict,
        fields: Map<String, Object?>.from(remote),
      );
    }

    // Regle 1 — le client etait a la salle.
    if (entity == SyncEntityType.setLog && role == UserRole.client) {
      return MergeOutcome(
        resolution: ConflictResolution.localWins,
        fields: Map<String, Object?>.from(local),
      );
    }

    // Regle 2 — proprietaire d'ecriture unique.
    switch (entity.writer) {
      case SyncWriter.coach:
      case SyncWriter.client:
        final bool iOwnIt = entity.isWrittenBy(role);
        return MergeOutcome(
          resolution: iOwnIt
              ? ConflictResolution.localWins
              : ConflictResolution.remoteWins,
          fields: Map<String, Object?>.from(iOwnIt ? local : remote),
        );
      case SyncWriter.shared:
        break;
    }

    // Regle 3 — merge a 3 voies, uniquement pour les entites partagees.
    return MergeOutcome(
      resolution: ConflictResolution.merged,
      fields: threeWayMerge(base: base, local: local, remote: remote),
    );
  }

  /// Fusionne champ par champ.
  ///
  /// Pour chaque cle :
  /// - modifiee localement seulement -> valeur locale ;
  /// - modifiee cote serveur seulement -> valeur serveur ;
  /// - modifiee des deux cotes -> valeur serveur (le serveur tranche, c'est
  ///   la lecture la plus sure pour une donnee qu'on ne possede pas seul) ;
  /// - inchangee -> valeur de base.
  static Map<String, Object?> threeWayMerge({
    required Map<String, Object?> base,
    required Map<String, Object?> local,
    required Map<String, Object?> remote,
  }) {
    const DeepCollectionEquality equality = DeepCollectionEquality();
    final Set<String> keys = <String>{
      ...base.keys,
      ...local.keys,
      ...remote.keys,
    };

    final Map<String, Object?> result = <String, Object?>{};
    for (final String key in keys) {
      final Object? baseValue = base[key];
      final Object? localValue = local[key];
      final Object? remoteValue = remote[key];

      final bool localChanged =
          local.containsKey(key) && !equality.equals(localValue, baseValue);
      final bool remoteChanged =
          remote.containsKey(key) && !equality.equals(remoteValue, baseValue);

      if (localChanged && !remoteChanged) {
        result[key] = localValue;
      } else if (remoteChanged) {
        result[key] = remoteValue;
      } else {
        result[key] = remote.containsKey(key) ? remoteValue : baseValue;
      }
    }
    return result;
  }

  /// Champs reellement modifies en local par rapport a la derniere version
  /// connue du serveur. Sert aussi a n'envoyer que le delta en `PATCH`.
  static Map<String, Object?> localDelta({
    required Map<String, Object?> base,
    required Map<String, Object?> local,
  }) {
    const DeepCollectionEquality equality = DeepCollectionEquality();
    final Map<String, Object?> delta = <String, Object?>{};
    for (final MapEntry<String, Object?> entry in local.entries) {
      if (!equality.equals(entry.value, base[entry.key])) {
        delta[entry.key] = entry.value;
      }
    }
    return delta;
  }
}
