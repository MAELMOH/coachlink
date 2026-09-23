import 'package:drift/drift.dart';

/// Colonnes de synchronisation communes a toute entite repliquee localement.
///
/// - [remoteUpdatedAt] : `updated_at` du serveur pour cet enregistrement.
///   Le Tech Lead a tranche le 2026-09-22 : `/sync` versionne **par
///   enregistrement**, pas par colonne.
/// - [isDirty] : l'enregistrement porte des modifications locales non encore
///   acquittees par le serveur.
/// - [baseSnapshot] : copie JSON de la derniere version **connue du serveur**.
///   C'est la troisieme branche du merge a 3 voies (base / local / serveur) :
///   sans elle, impossible de savoir quels champs l'utilisateur a reellement
///   modifies hors ligne.
mixin SyncableTable on Table {
  DateTimeColumn get remoteUpdatedAt => dateTime().nullable()();
  DateTimeColumn get localUpdatedAt => dateTime()();
  BoolColumn get isDirty => boolean().withDefault(const Constant(false))();
  BoolColumn get isDeleted => boolean().withDefault(const Constant(false))();
  TextColumn get baseSnapshot => text().nullable()();
}

/// File de synchronisation offline (ARCHITECTURE.md 8).
///
/// L'[idempotencyKey] est generee **a l'enfilement** et persistee : un rejeu
/// apres redemarrage de l'app doit reutiliser la meme cle, sinon le serveur
/// cree un doublon.
class PendingOperations extends Table {
  TextColumn get id => text()();
  TextColumn get entityType => text()();
  TextColumn get entityId => text()();

  /// `create` | `update` | `delete`
  TextColumn get operation => text()();

  TextColumn get method => text()();
  TextColumn get path => text()();

  /// Corps JSON serialise.
  TextColumn get payload => text()();

  TextColumn get idempotencyKey => text()();

  /// Garantit l'ordre d'emission (FIFO strict par entite).
  IntColumn get sequence => integer().autoIncrement()();

  IntColumn get attempts => integer().withDefault(const Constant(0))();
  DateTimeColumn get createdAt => dateTime()();
  DateTimeColumn get nextAttemptAt => dateTime().nullable()();
  TextColumn get lastErrorCode => text().nullable()();
  TextColumn get lastErrorMessage => text().nullable()();

  /// Operation definitivement rejetee par le serveur : conservee pour
  /// diagnostic et remontee a l'utilisateur, mais plus rejouee.
  BoolColumn get isDead => boolean().withDefault(const Constant(false))();

  @override
  List<Set<Column<Object>>> get uniqueKeys => <Set<Column<Object>>>[
        <Column<Object>>{id},
        <Column<Object>>{idempotencyKey},
      ];
}

/// Curseur de synchronisation : valeur de `since` pour `GET /sync?since=`.
class SyncCheckpoints extends Table {
  TextColumn get scope => text()();
  DateTimeColumn get lastSyncedAt => dateTime().nullable()();
  DateTimeColumn get lastAttemptAt => dateTime().nullable()();

  @override
  Set<Column<Object>> get primaryKey => <Column<Object>>{scope};
}

class LocalExercises extends Table with SyncableTable {
  TextColumn get id => text()();
  TextColumn get ownerCoachId => text().nullable()();
  TextColumn get name => text()();
  TextColumn get description => text().nullable()();

  /// Listes serialisees en JSON (SQLite n'a pas de type tableau).
  TextColumn get primaryMuscles => text().withDefault(const Constant('[]'))();
  TextColumn get secondaryMuscles => text().withDefault(const Constant('[]'))();
  TextColumn get equipment => text().nullable()();
  TextColumn get mechanic => text().nullable()();
  TextColumn get force => text().nullable()();
  TextColumn get imageKeys => text().withDefault(const Constant('[]'))();
  TextColumn get videoKey => text().nullable()();

  /// `public_domain` | `coach_owned` — rend l'audit juridique possible
  /// jusque dans le cache local (ARCHITECTURE.md 6).
  TextColumn get mediaLicense => text().nullable()();
  TextColumn get source => text().nullable()();
  BoolColumn get isPublic => boolean().withDefault(const Constant(true))();

  @override
  Set<Column<Object>> get primaryKey => <Column<Object>>{id};
}

class LocalPrograms extends Table with SyncableTable {
  TextColumn get id => text()();
  TextColumn get coachId => text()();
  TextColumn get clientId => text().nullable()();
  TextColumn get name => text()();
  TextColumn get description => text().nullable()();
  DateTimeColumn get startsOn => dateTime().nullable()();
  DateTimeColumn get endsOn => dateTime().nullable()();

  /// `draft` | `published` | `archived`
  TextColumn get status => text().withDefault(const Constant('draft'))();

  @override
  Set<Column<Object>> get primaryKey => <Column<Object>>{id};
}

class LocalProgramSessions extends Table with SyncableTable {
  TextColumn get id => text()();
  TextColumn get programId => text()();
  TextColumn get name => text()();
  IntColumn get dayIndex => integer().nullable()();
  DateTimeColumn get scheduledDate => dateTime().nullable()();
  IntColumn get orderIndex => integer().withDefault(const Constant(0))();
  TextColumn get notes => text().nullable()();

  @override
  Set<Column<Object>> get primaryKey => <Column<Object>>{id};
}

class LocalSessionExercises extends Table with SyncableTable {
  TextColumn get id => text()();
  TextColumn get programSessionId => text()();
  TextColumn get exerciseId => text()();
  IntColumn get orderIndex => integer().withDefault(const Constant(0))();
  IntColumn get targetSets => integer().nullable()();
  TextColumn get targetReps => text().nullable()();
  RealColumn get targetLoadKg => real().nullable()();
  IntColumn get restSeconds => integer().nullable()();
  TextColumn get tempo => text().nullable()();
  TextColumn get coachNotes => text().nullable()();

  @override
  Set<Column<Object>> get primaryKey => <Column<Object>>{id};
}

class LocalWorkoutLogs extends Table with SyncableTable {
  TextColumn get id => text()();
  TextColumn get clientId => text()();
  TextColumn get programSessionId => text().nullable()();
  DateTimeColumn get performedAt => dateTime()();

  /// `planned` | `in_progress` | `completed` | `skipped`
  TextColumn get status => text().withDefault(const Constant('planned'))();
  IntColumn get durationSeconds => integer().nullable()();
  TextColumn get clientNotes => text().nullable()();
  IntColumn get rpe => integer().nullable()();

  /// Volume estime localement pour l'affichage hors ligne. Le serveur fait
  /// autorite a la synchro (ARCHITECTURE.md 4).
  RealColumn get totalVolumeKg => real().withDefault(const Constant(0))();

  /// Snapshot JSON de la seance telle qu'elle existait au moment de
  /// l'execution : si le coach modifie ou archive le programme entre-temps,
  /// le log du client reste rattachable et n'est jamais rejete.
  TextColumn get sessionSnapshot => text().nullable()();

  @override
  Set<Column<Object>> get primaryKey => <Column<Object>>{id};
}

class LocalSetLogs extends Table with SyncableTable {
  TextColumn get id => text()();
  TextColumn get workoutLogId => text()();
  TextColumn get sessionExerciseId => text()();
  IntColumn get setIndex => integer()();
  IntColumn get repsDone => integer().nullable()();
  RealColumn get loadKg => real().nullable()();
  BoolColumn get isCompleted => boolean().withDefault(const Constant(false))();
  IntColumn get restTakenSeconds => integer().nullable()();

  @override
  Set<Column<Object>> get primaryKey => <Column<Object>>{id};
}

class LocalBodyMeasurements extends Table with SyncableTable {
  TextColumn get id => text()();
  TextColumn get clientId => text()();
  DateTimeColumn get measuredAt => dateTime()();
  RealColumn get weightKg => real().nullable()();
  RealColumn get bodyFatPct => real().nullable()();
  RealColumn get waistCm => real().nullable()();
  RealColumn get hipCm => real().nullable()();
  RealColumn get chestCm => real().nullable()();
  RealColumn get armCm => real().nullable()();
  RealColumn get thighCm => real().nullable()();
  TextColumn get source => text().withDefault(const Constant('client'))();

  @override
  Set<Column<Object>> get primaryKey => <Column<Object>>{id};
}

class LocalProgressPhotos extends Table with SyncableTable {
  TextColumn get id => text()();
  TextColumn get clientId => text()();
  DateTimeColumn get takenAt => dateTime()();
  TextColumn get storageKey => text().nullable()();
  TextColumn get localPath => text().nullable()();

  /// `front` | `side` | `back`
  TextColumn get angle => text().nullable()();

  /// **Defaut `false`, non negociable** (ARCHITECTURE.md 4 et 5.1).
  /// Le passage a `true` ne peut resulter que d'une action explicite de
  /// l'utilisateur, jamais d'un effet de bord de synchronisation.
  BoolColumn get sharedWithCoach =>
      boolean().withDefault(const Constant(false))();

  @override
  Set<Column<Object>> get primaryKey => <Column<Object>>{id};
}
