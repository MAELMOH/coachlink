import 'package:flutter/foundation.dart';

/// Finalites de consentement (ARCHITECTURE.md 4 et 5.2).
enum ConsentPurpose {
  /// Conditions generales - obligatoire.
  tos('tos', isMandatory: true),

  /// Politique de confidentialite - obligatoire.
  privacy('privacy', isMandatory: true),

  /// Traitement des donnees de sante (poids, mensurations, nutrition) -
  /// obligatoire : sans lui, le produit n'a pas d'objet.
  healthData('health_data', isMandatory: true),

  /// Photos de progression - **facultatif, opt-in decoche par defaut**.
  progressPhotos('progress_photos', isMandatory: false),

  /// Communications marketing - **facultatif, opt-in decoche par defaut**.
  marketing('marketing', isMandatory: false);

  const ConsentPurpose(this.wireValue, {required this.isMandatory});

  final String wireValue;

  /// Si `true`, l'API repond `403 CONSENT_REQUIRED` tant qu'il manque.
  final bool isMandatory;

  static ConsentPurpose? fromWire(String value) {
    for (final ConsentPurpose purpose in ConsentPurpose.values) {
      if (purpose.wireValue == value) {
        return purpose;
      }
    }
    return null;
  }

  /// Les trois consentements bloquants.
  static List<ConsentPurpose> get mandatory => ConsentPurpose.values
      .where((ConsentPurpose p) => p.isMandatory)
      .toList(growable: false);

  static List<ConsentPurpose> get optional => ConsentPurpose.values
      .where((ConsentPurpose p) => !p.isMandatory)
      .toList(growable: false);
}

@immutable
class Consent {
  const Consent({
    required this.purpose,
    required this.granted,
    this.version,
    this.grantedAt,
    this.revokedAt,
  });

  final ConsentPurpose purpose;
  final bool granted;
  final String? version;
  final DateTime? grantedAt;
  final DateTime? revokedAt;

  bool get isActive => granted && revokedAt == null;

  Map<String, Object?> toJson() => <String, Object?>{
        'purpose': purpose.wireValue,
        'granted': granted,
        if (version != null) 'version': version,
      };

  static Consent? fromJson(Map<String, Object?> json) {
    final ConsentPurpose? purpose =
        ConsentPurpose.fromWire('${json['purpose']}');
    if (purpose == null) {
      return null;
    }
    return Consent(
      purpose: purpose,
      granted: json['granted'] == true,
      version: json['version'] as String?,
      grantedAt: _parseDate(json['granted_at']),
      revokedAt: _parseDate(json['revoked_at']),
    );
  }

  static DateTime? _parseDate(Object? value) =>
      value is String ? DateTime.tryParse(value)?.toUtc() : null;
}

/// Etat des consentements d'un utilisateur.
@immutable
class ConsentState {
  const ConsentState(this.consents);

  /// Etat initial : **tout est decoche**, y compris les facultatifs.
  /// C'est le defaut voulu, pas une commodite d'implementation.
  const ConsentState.empty() : consents = const <ConsentPurpose, Consent>{};

  final Map<ConsentPurpose, Consent> consents;

  bool isGranted(ConsentPurpose purpose) =>
      consents[purpose]?.isActive ?? false;

  /// Vrai quand les trois consentements obligatoires sont accordes.
  /// Tant que c'est faux, l'API renvoie `403 CONSENT_REQUIRED` et la
  /// navigation doit rester bloquee sur l'ecran de consentement.
  bool get hasMandatoryConsents => ConsentPurpose.mandatory.every(isGranted);

  /// Les photos de progression ne peuvent meme pas etre prises sans cet accord.
  bool get allowsProgressPhotos => isGranted(ConsentPurpose.progressPhotos);

  List<ConsentPurpose> get missingMandatory => ConsentPurpose.mandatory
      .where((ConsentPurpose p) => !isGranted(p))
      .toList(growable: false);

  ConsentState withConsent(Consent consent) {
    return ConsentState(<ConsentPurpose, Consent>{
      ...consents,
      consent.purpose: consent,
    });
  }

  static ConsentState fromJsonList(List<Map<String, Object?>> items) {
    final Map<ConsentPurpose, Consent> map = <ConsentPurpose, Consent>{};
    for (final Map<String, Object?> item in items) {
      final Consent? consent = Consent.fromJson(item);
      if (consent != null) {
        map[consent.purpose] = consent;
      }
    }
    return ConsentState(map);
  }
}
