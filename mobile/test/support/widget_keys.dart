/// Stable widget keys shared by widget tests and `integration_test`.
///
/// Integration tests must not locate widgets by their visible text. The app is
/// FR-first with EN planned (ARCHITECTURE.md §2.1), so every `find.text('Se
/// connecter')` breaks on the first wording tweak or the day the EN locale lands —
/// and it breaks in a way that looks like a product bug rather than a test bug.
///
/// Keys are the contract between QA and `front`. Convention: `<feature>-<element>`,
/// kebab-case, with indices appended for repeated rows.
///
/// Kept in `test/` for now so the suite is self-contained. If `front` prefers these
/// live in `lib/core/testing/` so widgets reference the same constants instead of
/// re-typing the strings, that is strictly better — say so and this file becomes a
/// re-export.
library;

import 'package:flutter/widgets.dart';

class K {
  const K._();

  // --- auth -----------------------------------------------------------------
  static const loginEmail = Key('login-email-field');
  static const loginPassword = Key('login-password-field');
  static const loginSubmit = Key('login-submit');
  static const registerRoleCoach = Key('register-role-coach');
  static const registerRoleClient = Key('register-role-client');
  static const registerSubmit = Key('register-submit');

  // --- RGPD consent (blocking screen, §5.2) ---------------------------------
  static const consentTos = Key('consent-tos-checkbox');
  static const consentPrivacy = Key('consent-privacy-checkbox');
  static const consentHealth = Key('consent-health-checkbox');
  static const consentPhotos = Key('consent-photos-checkbox');
  static const consentMarketing = Key('consent-marketing-checkbox');
  static const consentSubmit = Key('consent-submit');

  // --- "Mes données" --------------------------------------------------------
  static const myDataExport = Key('my-data-export');
  static const myDataDelete = Key('my-data-delete-account');
  static const myDataRevokeHealth = Key('my-data-revoke-health');

  // --- invitation -----------------------------------------------------------
  static const coachInviteGenerate = Key('coach-invite-generate');
  static const coachInviteCode = Key('coach-invite-code-text');
  static const coachInviteModePresentiel = Key('coach-invite-mode-presentiel');
  static const coachInviteModeDistance = Key('coach-invite-mode-distance');
  static const inviteAcceptCode = Key('invite-accept-code-field');
  static const inviteAcceptSubmit = Key('invite-accept-submit');

  // --- coach ----------------------------------------------------------------
  static const coachDashboard = Key('coach-dashboard');
  static const coachClientProgressChart = Key('coach-client-progress-chart');
  static const programEditorPublish = Key('program-editor-publish');

  // --- client workout -------------------------------------------------------
  static const clientTodaySession = Key('client-today-session');
  static const workoutStart = Key('workout-start');
  static const workoutFinish = Key('workout-finish');

  /// One checkbox per set: `set-log-checkbox-<exerciseIndex>-<setIndex>`.
  static Key setLogCheckbox(int exercise, int set) =>
      Key('set-log-checkbox-$exercise-$set');
  static Key setLogReps(int exercise, int set) => Key('set-log-reps-$exercise-$set');
  static Key setLogLoad(int exercise, int set) => Key('set-log-load-$exercise-$set');

  // --- offline / sync -------------------------------------------------------
  static const syncStatusBanner = Key('sync-status-banner');
  static const syncPendingCount = Key('sync-pending-count');
  static const offlineBanner = Key('offline-banner');

  // --- coach view of client -------------------------------------------------
  static const clientDetailMeasurements = Key('client-detail-measurements');
  static const clientDetailPhotos = Key('client-detail-photos');
}

/// Keys that must exist on every build for the critical journey to be testable.
///
/// `front` can run this list against a screen to check nothing was renamed.
const criticalJourneyKeys = <Key>[
  K.loginEmail,
  K.loginPassword,
  K.loginSubmit,
  K.consentTos,
  K.consentPrivacy,
  K.consentHealth,
  K.consentSubmit,
  K.coachInviteGenerate,
  K.inviteAcceptCode,
  K.inviteAcceptSubmit,
  K.programEditorPublish,
  K.clientTodaySession,
  K.workoutFinish,
  K.syncStatusBanner,
  K.coachClientProgressChart,
];
