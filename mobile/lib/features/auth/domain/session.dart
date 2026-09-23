import 'package:flutter/foundation.dart';

import '../../../core/sync/entity_ownership.dart';
import '../../consent/domain/consent.dart';

/// Mode de coaching du lien coach-client (ARCHITECTURE.md 4).
enum CoachingMode {
  /// Suivi simplifie, **messagerie masquee**.
  presentiel('presentiel'),

  /// Suivi complet, messagerie active.
  distance('distance');

  const CoachingMode(this.wireValue);

  final String wireValue;

  static CoachingMode? fromWire(String? value) {
    for (final CoachingMode mode in CoachingMode.values) {
      if (mode.wireValue == value) {
        return mode;
      }
    }
    return null;
  }

  bool get allowsMessaging => this == CoachingMode.distance;
}

enum SubscriptionStatus {
  trialing('trialing'),
  active('active'),
  pastDue('past_due'),
  canceled('canceled');

  const SubscriptionStatus(this.wireValue);

  final String wireValue;

  static SubscriptionStatus? fromWire(String? value) {
    for (final SubscriptionStatus status in SubscriptionStatus.values) {
      if (status.wireValue == value) {
        return status;
      }
    }
    return null;
  }
}

/// Etape du parcours, qui pilote les redirections du routeur.
enum SessionStage {
  /// Chargement initial : jetons pas encore relus depuis le Keychain.
  unknown,

  unauthenticated,

  /// Authentifie mais consentements obligatoires manquants.
  /// L'API repond `403 CONSENT_REQUIRED` : toute navigation metier est
  /// bloquee tant qu'on n'est pas sorti de cet etat.
  consentRequired,

  ready,
}

@immutable
class Session {
  const Session({
    required this.stage,
    this.userId,
    this.role,
    this.email,
    this.firstName,
    this.coachingMode,
    this.consents = const ConsentState.empty(),
    this.subscriptionStatus,
    this.trialEndsAt,
    this.offersNutrition = false,
    this.timezone,
  });

  const Session.unknown() : this(stage: SessionStage.unknown);
  const Session.signedOut() : this(stage: SessionStage.unauthenticated);

  final SessionStage stage;
  final String? userId;
  final UserRole? role;
  final String? email;
  final String? firstName;

  /// Mode du lien coach-client actif (cote client), ou mode par defaut du
  /// coach. `null` tant qu'aucun lien n'existe.
  final CoachingMode? coachingMode;

  final ConsentState consents;
  final SubscriptionStatus? subscriptionStatus;
  final DateTime? trialEndsAt;

  /// Le coach propose-t-il la nutrition ? Masque la feature de bout en bout.
  final bool offersNutrition;

  /// Fuseau IANA du device, ex. `Europe/Paris`.
  ///
  /// Envoye a la connexion et mis a jour s'il change : « la seance du jour »
  /// se resout dans le fuseau de l'utilisateur, pas en UTC, sinon un client
  /// a 23h voit la seance du lendemain (arbitrage Tech Lead, 2026-09-22).
  final String? timezone;

  bool get isAuthenticated =>
      stage == SessionStage.ready || stage == SessionStage.consentRequired;

  bool get isCoach => role == UserRole.coach;
  bool get isClient => role == UserRole.client;

  /// La messagerie est masquee en coaching presentiel.
  bool get canUseMessaging => coachingMode?.allowsMessaging ?? false;

  /// Jours restants d'essai, `null` si sans objet.
  int? trialDaysRemaining({DateTime? now}) {
    final DateTime? endsAt = trialEndsAt;
    if (endsAt == null) {
      return null;
    }
    final DateTime reference = (now ?? DateTime.now()).toUtc();
    final int days = endsAt.toUtc().difference(reference).inDays;
    return days < 0 ? 0 : days;
  }

  bool isTrialExpired({DateTime? now}) {
    final DateTime? endsAt = trialEndsAt;
    if (endsAt == null) {
      return false;
    }
    return (now ?? DateTime.now()).toUtc().isAfter(endsAt.toUtc());
  }

  /// Mode lecture seule : essai termine sans abonnement.
  ///
  /// On ne coupe **jamais** l'acces a ses propres donnees (exigence RGPD,
  /// ARCHITECTURE.md 7) : la consultation du programme et de l'historique
  /// reste ouverte, seules les ecritures sont fermees.
  bool get isReadOnly {
    if (role != UserRole.client) {
      return false;
    }
    final SubscriptionStatus? status = subscriptionStatus;
    if (status == SubscriptionStatus.active) {
      return false;
    }
    if (status == SubscriptionStatus.trialing) {
      return isTrialExpired();
    }
    return status == SubscriptionStatus.pastDue ||
        status == SubscriptionStatus.canceled ||
        isTrialExpired();
  }

  Session copyWith({
    SessionStage? stage,
    String? userId,
    UserRole? role,
    String? email,
    String? firstName,
    CoachingMode? coachingMode,
    ConsentState? consents,
    SubscriptionStatus? subscriptionStatus,
    DateTime? trialEndsAt,
    bool? offersNutrition,
    String? timezone,
  }) {
    return Session(
      stage: stage ?? this.stage,
      userId: userId ?? this.userId,
      role: role ?? this.role,
      email: email ?? this.email,
      firstName: firstName ?? this.firstName,
      coachingMode: coachingMode ?? this.coachingMode,
      consents: consents ?? this.consents,
      subscriptionStatus: subscriptionStatus ?? this.subscriptionStatus,
      trialEndsAt: trialEndsAt ?? this.trialEndsAt,
      offersNutrition: offersNutrition ?? this.offersNutrition,
      timezone: timezone ?? this.timezone,
    );
  }

  /// Recalcule l'etape a partir des consentements : l'etape n'est jamais
  /// posee a la main, elle derive de l'etat reel.
  Session withRecomputedStage() {
    if (userId == null) {
      return const Session.signedOut();
    }
    return copyWith(
      stage: consents.hasMandatoryConsents
          ? SessionStage.ready
          : SessionStage.consentRequired,
    );
  }
}
