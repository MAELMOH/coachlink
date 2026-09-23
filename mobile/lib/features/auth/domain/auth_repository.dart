import '../../../core/storage/secure_store.dart';
import '../../../core/sync/entity_ownership.dart';
import '../../consent/domain/consent.dart';
import 'session.dart';

/// Resultat d'une authentification reussie.
class AuthResult {
  const AuthResult({required this.tokens, required this.session});

  final AuthTokens tokens;
  final Session session;
}

/// Contrat d'authentification.
///
/// Deux implementations : `HttpAuthRepository` (API reelle) et
/// `FakeAuthRepository` (source simulee tant que le backend n'expose pas son
/// OpenAPI). La couche presentation ne voit que cette interface.
abstract class AuthRepository {
  /// [timezone] : fuseau IANA du device, transmis des la connexion.
  Future<AuthResult> signIn({
    required String email,
    required String password,
    required String timezone,
  });

  Future<AuthResult> signUp({
    required String email,
    required String password,
    required UserRole role,
    required String timezone,
    String? firstName,
    String? lastName,
  });

  /// Recharge la session courante (`GET /me`), notamment apres un demarrage
  /// a froid ou un changement de consentement.
  Future<Session> loadSession();

  /// Met a jour le fuseau cote serveur (voyage, changement de reglage).
  Future<void> updateTimezone(String timezone);

  Future<ConsentState> fetchConsents();

  /// Enregistre les choix de consentement. Les finalites facultatives non
  /// cochees sont envoyees explicitement a `false` : un consentement absent
  /// et un consentement refuse ne se traitent pas de la meme maniere.
  Future<ConsentState> submitConsents(Map<ConsentPurpose, bool> choices);

  Future<void> revokeConsent(ConsentPurpose purpose);

  /// `POST /me/data-export` - declenche l'export RGPD.
  Future<void> requestDataExport();

  /// `POST /me/delete-account` - ouvre la fenetre de retractation de 7 jours.
  Future<void> requestAccountDeletion();

  Future<void> signOut();
}
