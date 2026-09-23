import 'package:flutter/widgets.dart';

/// Registre central des `Key` de widgets.
///
/// Convention retenue avec l'agent QA (2026-09-22) : `<feature>-<element>` en
/// kebab-case. Les tests d'integration ciblent **toujours** une cle, jamais un
/// libelle : un texte change au premier ajustement de wording ou de traduction,
/// une cle non.
///
/// Toute cle ajoutee ici doit l'etre en meme temps que le widget, pas apres :
/// retrofitter des cles sur des ecrans existants coute bien plus cher.
abstract final class K {
  // --- Authentification ---
  static const Key loginEmailField = Key('login-email-field');
  static const Key loginPasswordField = Key('login-password-field');
  static const Key loginSubmit = Key('login-submit');
  static const Key signupEmailField = Key('signup-email-field');
  static const Key signupPasswordField = Key('signup-password-field');
  static const Key signupRoleCoach = Key('signup-role-coach');
  static const Key signupRoleClient = Key('signup-role-client');
  static const Key signupSubmit = Key('signup-submit');
  static const Key logoutButton = Key('logout-button');

  // --- Consentement RGPD ---
  static const Key consentTosCheckbox = Key('consent-tos-checkbox');
  static const Key consentPrivacyCheckbox = Key('consent-privacy-checkbox');
  static const Key consentHealthCheckbox = Key('consent-health-checkbox');
  static const Key consentPhotosCheckbox = Key('consent-photos-checkbox');
  static const Key consentMarketingCheckbox = Key('consent-marketing-checkbox');
  static const Key consentSubmit = Key('consent-submit');

  // --- Mes donnees (RGPD) ---
  static const Key myDataExport = Key('my-data-export');
  static const Key myDataDelete = Key('my-data-delete');
  static Key myDataRevoke(String purpose) => Key('my-data-revoke-$purpose');

  // --- Essai / abonnement ---
  static const Key trialBanner = Key('trial-banner');
  static const Key readOnlyBadge = Key('read-only-badge');

  // --- Coach ---
  static const Key coachDashboard = Key('coach-dashboard');
  static Key coachClientCard(String clientId) =>
      Key('coach-client-card-$clientId');
  static const Key coachInviteGenerate = Key('coach-invite-generate');
  static const Key coachInviteCodeText = Key('coach-invite-code-text');
  static const Key coachInviteShare = Key('coach-invite-share');
  static const Key coachInviteModePresentiel =
      Key('coach-invite-mode-presentiel');
  static const Key coachInviteModeDistance = Key('coach-invite-mode-distance');
  static const Key coachClientProgressChart =
      Key('coach-client-progress-chart');

  // --- Invitation cote client ---
  static const Key inviteAcceptCodeField = Key('invite-accept-code-field');
  static const Key inviteAcceptSubmit = Key('invite-accept-submit');

  // --- Editeur de programme ---
  static const Key programEditorPublish = Key('program-editor-publish');
  static const Key programEditorAddSession = Key('program-editor-add-session');
  static Key programEditorSession(int index) =>
      Key('program-editor-session-$index');
  static Key programEditorExercise(int sessionIndex, int exerciseIndex) =>
      Key('program-editor-exercise-$sessionIndex-$exerciseIndex');

  // --- Bibliotheque d'exercices ---
  static const Key exerciseSearchField = Key('exercise-search-field');
  static Key exerciseCard(String exerciseId) =>
      Key('exercise-card-$exerciseId');
  static const Key exerciseCreateSubmit = Key('exercise-create-submit');
  static const Key exerciseMediaUpload = Key('exercise-media-upload');

  // --- Client : seance ---
  static const Key clientTodaySession = Key('client-today-session');
  static const Key clientWeekView = Key('client-week-view');
  static const Key workoutStart = Key('workout-start');
  static const Key workoutFinish = Key('workout-finish');
  static const Key restTimer = Key('rest-timer');

  /// Une cle par serie : `<exerciceIndex>-<serieIndex>`.
  static Key setLogCheckbox(int exerciseIndex, int setIndex) =>
      Key('set-log-checkbox-$exerciseIndex-$setIndex');
  static Key setLogReps(int exerciseIndex, int setIndex) =>
      Key('set-log-reps-$exerciseIndex-$setIndex');
  static Key setLogLoad(int exerciseIndex, int setIndex) =>
      Key('set-log-load-$exerciseIndex-$setIndex');

  // --- Mesures et photos ---
  static const Key measurementWeightField = Key('measurement-weight-field');
  static const Key measurementSubmit = Key('measurement-submit');
  static Key progressPhotoShareToggle(String photoId) =>
      Key('progress-photo-share-toggle-$photoId');
  static const Key progressPhotoShareConfirm =
      Key('progress-photo-share-confirm');

  // --- Messagerie ---
  static const Key messageInput = Key('message-input');
  static const Key messageSend = Key('message-send');

  // --- Transverse ---
  static const Key syncStatusBanner = Key('sync-status-banner');
  static const Key offlineBanner = Key('offline-banner');
  static const Key errorRetryButton = Key('error-retry-button');
  static const Key loadingIndicator = Key('loading-indicator');
  static const Key emptyState = Key('empty-state');
}
