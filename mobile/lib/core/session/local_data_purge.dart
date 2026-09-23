import 'dart:io';

import '../database/app_database.dart';
import '../storage/secure_store.dart';

/// Purge complete des donnees locales au logout (ARCHITECTURE.md 5.1).
///
/// L'ordre compte, et chaque etape est defensive : on ne veut **aucun** chemin
/// par lequel une base de donnees de sante survivrait a une deconnexion.
///
/// 1. Vider les tables — si le fichier ne peut pas etre supprime (verrou
///    plateforme), les donnees ne subsistent pas pour autant.
/// 2. Fermer la base — sinon le fichier reste verrouille.
/// 3. Supprimer le fichier et ses journaux WAL/SHM — un `-wal` oublie contient
///    des pages de donnees en clair du point de vue applicatif.
/// 4. Detruire la passphrase du Keychain/Keystore — ce qui rend illisible tout
///    residu eventuel, meme en cas d'echec des etapes precedentes.
/// 5. Effacer les jetons.
class LocalDataPurge {
  const LocalDataPurge({
    required SecureStore secureStore,
    required DatabaseKeyProvider keyProvider,
    required TokenStore tokenStore,
    Future<Directory> Function()? directoryProvider,
  })  : _secureStore = secureStore,
        _keyProvider = keyProvider,
        _tokenStore = tokenStore,
        _directoryProvider = directoryProvider ?? defaultDatabaseDirectory;

  final SecureStore _secureStore;
  final DatabaseKeyProvider _keyProvider;
  final TokenStore _tokenStore;
  final Future<Directory> Function() _directoryProvider;

  /// [database] peut etre `null` si la base n'a jamais ete ouverte.
  Future<PurgeReport> purge({AppDatabase? database}) async {
    final List<String> failures = <String>[];

    if (database != null) {
      await _attempt('wipe_tables', failures, database.wipe);
      await _attempt('close_database', failures, database.close);
    }

    await _attempt('delete_file', failures, () async {
      await deleteDatabaseFile(await _directoryProvider());
    });

    // Cette etape est la plus importante : meme si tout le reste a echoue,
    // detruire la cle rend les donnees residuelles inexploitables.
    await _attempt('destroy_key', failures, _keyProvider.destroy);
    await _attempt('clear_tokens', failures, _tokenStore.clear);
    await _attempt('clear_secure_store', failures, _secureStore.deleteAll);

    return PurgeReport(failedSteps: failures);
  }

  Future<void> _attempt(
    String step,
    List<String> failures,
    Future<void> Function() action,
  ) async {
    try {
      await action();
    } on Object {
      // On n'interrompt jamais la purge sur un echec d'etape : les etapes
      // suivantes sont precisement celles qui compensent.
      failures.add(step);
    }
  }
}

class PurgeReport {
  const PurgeReport({required this.failedSteps});

  final List<String> failedSteps;

  bool get isComplete => failedSteps.isEmpty;

  /// La cle a-t-elle bien ete detruite ? C'est le critere de securite
  /// minimal : sans cle, la base residuelle est un bloc de bruit.
  bool get keyDestroyed => !failedSteps.contains('destroy_key');

  @override
  String toString() => isComplete
      ? 'PurgeReport(complete)'
      : 'PurgeReport(failed: ${failedSteps.join(', ')})';
}
