/// Qui a le droit d'ecrire quoi.
///
/// Arbitrage Tech Lead du 2026-09-22 : **chaque entite a un proprietaire
/// d'ecriture unique**, ce qui rend la majorite des conflits impossibles par
/// construction. On n'a donc pas besoin d'un versionnement par colonne.
enum SyncWriter {
  /// Ecrit par le coach uniquement.
  coach,

  /// Ecrit par le client uniquement.
  client,

  /// Ecrit par les deux : seul cas ou un vrai merge est necessaire
  /// (profil, preferences).
  shared,
}

/// Role du compte connecte.
enum UserRole {
  coach,
  client;

  static UserRole? fromWire(String? value) {
    for (final UserRole role in UserRole.values) {
      if (role.name == value) {
        return role;
      }
    }
    return null;
  }
}

/// Entites repliquees localement et leur proprietaire d'ecriture.
enum SyncEntityType {
  program('program', SyncWriter.coach),
  programSession('program_session', SyncWriter.coach),
  sessionExercise('session_exercise', SyncWriter.coach),
  exercise('exercise', SyncWriter.coach),
  nutritionPlan('nutrition_plan', SyncWriter.coach),
  meal('meal', SyncWriter.coach),

  workoutLog('workout_log', SyncWriter.client),

  /// Cas special absolu : le client fait **toujours** foi sur `set_log`,
  /// c'est lui qui etait a la salle (ARCHITECTURE.md 8).
  setLog('set_log', SyncWriter.client),
  bodyMeasurement('body_measurement', SyncWriter.client),
  progressPhoto('progress_photo', SyncWriter.client),
  nutritionLog('nutrition_log', SyncWriter.client),

  userProfile('user_profile', SyncWriter.shared),
  consent('consent', SyncWriter.shared),
  message('message', SyncWriter.shared);

  const SyncEntityType(this.wireValue, this.writer);

  final String wireValue;
  final SyncWriter writer;

  static SyncEntityType? fromWire(String value) {
    for (final SyncEntityType type in SyncEntityType.values) {
      if (type.wireValue == value) {
        return type;
      }
    }
    return null;
  }

  /// Vrai si [role] est le proprietaire d'ecriture de cette entite.
  bool isWrittenBy(UserRole role) {
    switch (writer) {
      case SyncWriter.coach:
        return role == UserRole.coach;
      case SyncWriter.client:
        return role == UserRole.client;
      case SyncWriter.shared:
        return true;
    }
  }
}
