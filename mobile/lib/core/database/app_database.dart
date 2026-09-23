import 'dart:ffi';
import 'dart:io';

import 'package:drift/drift.dart';
import 'package:drift/native.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:sqlcipher_flutter_libs/sqlcipher_flutter_libs.dart';
import 'package:sqlite3/open.dart';
import 'package:sqlite3/sqlite3.dart';

import 'tables.dart';

part 'app_database.g.dart';

/// Base locale chiffree (SQLCipher) — ARCHITECTURE.md 5.1.
///
/// Trois invariants :
/// 1. La passphrase vient du Keychain/Keystore, jamais du code ni des
///    `SharedPreferences`.
/// 2. Le fichier est purge **entierement** au logout ([destroy]).
/// 3. Aucune donnee de sante n'est ecrite ailleurs que dans ce fichier.
@DriftDatabase(
  tables: <Type>[
    PendingOperations,
    SyncCheckpoints,
    LocalExercises,
    LocalPrograms,
    LocalProgramSessions,
    LocalSessionExercises,
    LocalWorkoutLogs,
    LocalSetLogs,
    LocalBodyMeasurements,
    LocalProgressPhotos,
  ],
)
class AppDatabase extends _$AppDatabase {
  AppDatabase(super.executor);

  /// Base en memoire, **pour les tests uniquement** : elle ne touche ni le
  /// Keychain ni le disque, ce qui rend les tests headless possibles.
  AppDatabase.inMemory() : super(NativeDatabase.memory());

  @override
  int get schemaVersion => 1;

  @override
  MigrationStrategy get migration => MigrationStrategy(
        beforeOpen: (OpeningDetails details) async {
          // Integrite referentielle : une seance orpheline n'a pas de sens.
          await customStatement('PRAGMA foreign_keys = ON');
        },
      );

  /// Vide toutes les tables. Utilise au logout, en complement de la
  /// destruction du fichier : si le fichier ne peut pas etre supprime
  /// (verrou Windows/iOS), les donnees ne subsistent pas pour autant.
  Future<void> wipe() async {
    await transaction(() async {
      for (final TableInfo<Table, dynamic> table in allTables) {
        await delete<Table, dynamic>(table).go();
      }
    });
  }
}

/// Nom du fichier de base. Un seul fichier, pour que la purge soit exhaustive.
const String kDatabaseFileName = 'coachlink.sqlite';

/// Ouvre la base chiffree avec la passphrase fournie.
///
/// [passphrase] doit provenir de `DatabaseKeyProvider.getOrCreate()`.
QueryExecutor openEncryptedDatabase({
  required String passphrase,
  required Future<Directory> Function() directoryProvider,
}) {
  return LazyDatabase(() async {
    _useSqlCipherLibraries();
    final Directory dir = await directoryProvider();
    final File file = File(p.join(dir.path, kDatabaseFileName));

    return NativeDatabase(
      file,
      setup: (Database db) {
        // La cle DOIT etre appliquee avant toute autre instruction.
        db.execute("PRAGMA key = '${_escapeForPragma(passphrase)}'");
        _assertCipherIsActive(db);
      },
    );
  });
}

Future<Directory> defaultDatabaseDirectory() =>
    getApplicationSupportDirectory();

/// Supprime physiquement le fichier de base et ses journaux WAL.
///
/// A appeler au logout, apres [AppDatabase.wipe] et avant la destruction de la
/// cle dans le Keychain.
Future<void> deleteDatabaseFile(Directory directory) async {
  for (final String suffix in <String>['', '-wal', '-shm', '-journal']) {
    final File file = File(p.join(directory.path, '$kDatabaseFileName$suffix'));
    if (file.existsSync()) {
      await file.delete();
    }
  }
}

bool _cipherLibrariesApplied = false;

void _useSqlCipherLibraries() {
  if (_cipherLibrariesApplied) {
    return;
  }
  _cipherLibrariesApplied = true;
  open
    ..overrideFor(OperatingSystem.android, openCipherOnAndroid)
    ..overrideFor(OperatingSystem.iOS, DynamicLibrary.process);
}

/// Verifie qu'on parle bien a SQLCipher et non au SQLite systeme.
///
/// Sans ce controle, une erreur de configuration produirait une base **en
/// clair** contenant des donnees de sante, sans aucun signal visible.
void _assertCipherIsActive(Database db) {
  final ResultSet result = db.select('PRAGMA cipher_version');
  if (result.isEmpty || '${result.first.values.first}'.isEmpty) {
    throw StateError(
      'SQLCipher indisponible : la base locale serait ecrite en clair. '
      'Ouverture refusee.',
    );
  }
}

/// Echappe la passphrase pour l'interpolation dans `PRAGMA key`.
/// `PRAGMA` n'accepte pas de parametre lie, d'ou cet echappement explicite.
String _escapeForPragma(String value) => value.replaceAll("'", "''");
