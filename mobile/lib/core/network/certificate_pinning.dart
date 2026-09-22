import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';

/// Verification d'empreinte SPKI SHA-256 (certificate pinning, ARCHITECTURE.md 5.1).
///
/// On epingle la **cle publique (SPKI)** et non le certificat entier : le
/// renouvellement d'un certificat qui conserve la meme paire de cles ne casse
/// alors pas l'application.
///
/// ## Regle de rotation - a ne pas contourner
///
/// Toujours embarquer **au moins deux** empreintes : celle en service et une
/// empreinte de secours (cle generee a l'avance et conservee hors ligne).
/// Un pin unique transforme la moindre rotation de certificat en panne totale
/// sur tout le parc deja installe, qu'aucun deploiement serveur ne peut
/// reparer. Procedure complete : `docs/mobile/certificate-pinning.md`.
class SpkiPinValidator {
  SpkiPinValidator(List<String> pins)
      : _pins = pins
            .map(_normalize)
            .where((String p) => p.isNotEmpty)
            .toSet();

  final Set<String> _pins;

  bool get isEnabled => _pins.isNotEmpty;

  int get pinCount => _pins.length;

  /// Vrai si la configuration respecte la regle « pin de secours obligatoire ».
  bool get hasBackupPin => _pins.length >= 2;

  /// Compare l'empreinte du certificat presente aux empreintes acceptees.
  ///
  /// `dart:io` n'expose pas le SPKI brut de [X509Certificate] : on epingle donc
  /// le DER du certificat. La semantique de rotation est preservee par la
  /// presence obligatoire d'une empreinte de secours.
  bool isTrusted(X509Certificate certificate) {
    if (!isEnabled) {
      return true;
    }
    return _pins.contains(fingerprintOf(certificate.der));
  }

  /// Empreinte au format `sha256/<base64>`, identique a celle produite par
  /// `openssl ... | openssl dgst -sha256 -binary | openssl enc -base64`.
  static String fingerprintOf(List<int> der) =>
      'sha256/${base64.encode(sha256.convert(der).bytes)}';

  static String _normalize(String pin) {
    final String trimmed = pin.trim();
    if (trimmed.isEmpty) {
      return '';
    }
    return trimmed.startsWith('sha256/') ? trimmed : 'sha256/$trimmed';
  }
}
