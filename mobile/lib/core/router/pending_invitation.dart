import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Code d'invitation capte avant authentification.
///
/// Parcours cible valide par le Tech Lead (2026-09-22) : lien -> store ->
/// premier lancement -> le code est retrouve et l'invitation s'applique.
/// Le *deferred deep linking* reel demanderait un SDK d'attribution tiers,
/// ecarte pour ses implications RGPD : le repli est donc la **saisie manuelle
/// du code a 8 caracteres**, toujours disponible sur l'ecran d'invitation.
class PendingInvitation extends StateNotifier<String?> {
  PendingInvitation() : super(null);

  /// Longueur du code (ARCHITECTURE.md 4 : 8 caracteres lisibles).
  static const int codeLength = 8;

  /// Caracteres ambigus exclus a la generation cote backend.
  static final RegExp _codePattern = RegExp(r'^[A-Z0-9]{8}$');

  static bool isValidCode(String value) =>
      _codePattern.hasMatch(normalize(value));

  /// Normalise une saisie utilisateur : majuscules, sans espaces ni tirets.
  static String normalize(String value) =>
      value.toUpperCase().replaceAll(RegExp(r'[\s-]'), '');

  void capture(String code) {
    final String normalized = normalize(code);
    if (normalized.isNotEmpty) {
      state = normalized;
    }
  }

  void clear() => state = null;
}

final StateNotifierProvider<PendingInvitation, String?>
    pendingInvitationProvider =
    StateNotifierProvider<PendingInvitation, String?>(
  (Ref ref) => PendingInvitation(),
);
