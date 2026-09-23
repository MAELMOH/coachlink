import 'dart:convert';
import 'dart:math';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Acces au Keychain (iOS) / Keystore (Android).
///
/// **Regle de securite (ARCHITECTURE.md 5.1)** : les jetons et la cle de
/// chiffrement de la base locale ne doivent JAMAIS transiter par
/// `SharedPreferences`. Tout passe par cette classe.
abstract class SecureStore {
  Future<String?> read(String key);
  Future<void> write(String key, String value);
  Future<void> delete(String key);

  /// Efface l'integralite du coffre. Appele au logout (voir `SessionPurge`).
  Future<void> deleteAll();
}

class FlutterSecureStore implements SecureStore {
  FlutterSecureStore([FlutterSecureStorage? storage])
      : _storage = storage ??
            const FlutterSecureStorage(
              aOptions: AndroidOptions(encryptedSharedPreferences: true),
              iOptions: IOSOptions(
                accessibility: KeychainAccessibility.first_unlock_this_device,
              ),
            );

  final FlutterSecureStorage _storage;

  @override
  Future<String?> read(String key) => _storage.read(key: key);

  @override
  Future<void> write(String key, String value) =>
      _storage.write(key: key, value: value);

  @override
  Future<void> delete(String key) => _storage.delete(key: key);

  @override
  Future<void> deleteAll() => _storage.deleteAll();
}

/// Implementation en memoire, pour les tests uniquement.
class InMemorySecureStore implements SecureStore {
  final Map<String, String> _values = <String, String>{};

  Map<String, String> get snapshot => Map<String, String>.unmodifiable(_values);

  @override
  Future<String?> read(String key) async => _values[key];

  @override
  Future<void> write(String key, String value) async => _values[key] = value;

  @override
  Future<void> delete(String key) async => _values.remove(key);

  @override
  Future<void> deleteAll() async => _values.clear();
}

/// Cles utilisees dans le coffre. Centralisees pour que la purge au logout
/// n'en oublie aucune.
abstract final class SecureKeys {
  static const String accessToken = 'auth.access_token';
  static const String refreshToken = 'auth.refresh_token';
  static const String accessTokenExpiry = 'auth.access_token_expires_at';
  static const String userId = 'auth.user_id';
  static const String userRole = 'auth.user_role';

  /// Passphrase SQLCipher de la base Drift locale.
  static const String databaseKey = 'db.sqlcipher_passphrase';
}

/// Jetons d'authentification.
class AuthTokens {
  const AuthTokens({
    required this.accessToken,
    required this.refreshToken,
    this.accessTokenExpiresAt,
  });

  final String accessToken;
  final String refreshToken;
  final DateTime? accessTokenExpiresAt;

  /// Marge de securite : on rafraichit avant l'expiration reelle pour eviter
  /// de partir en requete avec un jeton qui expire pendant le trajet reseau.
  static const Duration refreshLeeway = Duration(seconds: 30);

  bool get isExpired {
    final DateTime? expiry = accessTokenExpiresAt;
    if (expiry == null) {
      return false;
    }
    return DateTime.now().toUtc().isAfter(expiry.subtract(refreshLeeway));
  }
}

/// Lecture/ecriture des jetons dans le coffre.
class TokenStore {
  TokenStore(this._store);

  final SecureStore _store;

  Future<AuthTokens?> read() async {
    final String? access = await _store.read(SecureKeys.accessToken);
    final String? refresh = await _store.read(SecureKeys.refreshToken);
    if (access == null || refresh == null) {
      return null;
    }
    final String? rawExpiry = await _store.read(SecureKeys.accessTokenExpiry);
    return AuthTokens(
      accessToken: access,
      refreshToken: refresh,
      accessTokenExpiresAt:
          rawExpiry == null ? null : DateTime.tryParse(rawExpiry)?.toUtc(),
    );
  }

  Future<void> save(AuthTokens tokens) async {
    await _store.write(SecureKeys.accessToken, tokens.accessToken);
    await _store.write(SecureKeys.refreshToken, tokens.refreshToken);
    final DateTime? expiry = tokens.accessTokenExpiresAt;
    if (expiry == null) {
      await _store.delete(SecureKeys.accessTokenExpiry);
    } else {
      await _store.write(
        SecureKeys.accessTokenExpiry,
        expiry.toUtc().toIso8601String(),
      );
    }
  }

  Future<void> clear() async {
    await _store.delete(SecureKeys.accessToken);
    await _store.delete(SecureKeys.refreshToken);
    await _store.delete(SecureKeys.accessTokenExpiry);
  }
}

/// Fournit (et cree a la premiere ouverture) la passphrase SQLCipher.
///
/// La cle n'existe qu'au Keychain/Keystore : si l'utilisateur se deconnecte,
/// elle est detruite en meme temps que le fichier de base, ce qui rend les
/// donnees residuelles illisibles meme si le fichier survivait.
class DatabaseKeyProvider {
  DatabaseKeyProvider(this._store, {Random? random})
      : _random = random ?? Random.secure();

  final SecureStore _store;
  final Random _random;

  static const int _keyLengthBytes = 32;

  Future<String> getOrCreate() async {
    final String? existing = await _store.read(SecureKeys.databaseKey);
    if (existing != null && existing.isNotEmpty) {
      return existing;
    }
    final String generated = _generateKey();
    await _store.write(SecureKeys.databaseKey, generated);
    return generated;
  }

  Future<void> destroy() => _store.delete(SecureKeys.databaseKey);

  String _generateKey() {
    final List<int> bytes = List<int>.generate(
      _keyLengthBytes,
      (_) => _random.nextInt(256),
    );
    return base64UrlEncode(bytes);
  }
}

final Provider<SecureStore> secureStoreProvider = Provider<SecureStore>(
  (Ref ref) => FlutterSecureStore(),
);

final Provider<TokenStore> tokenStoreProvider = Provider<TokenStore>(
  (Ref ref) => TokenStore(ref.watch(secureStoreProvider)),
);

final Provider<DatabaseKeyProvider> databaseKeyProvider =
    Provider<DatabaseKeyProvider>(
  (Ref ref) => DatabaseKeyProvider(ref.watch(secureStoreProvider)),
);
