import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/config/app_config.dart';
import '../../../core/database/app_database.dart';
import '../../../core/error/api_error.dart';
import '../../../core/network/auth_interceptor.dart';
import '../../../core/network/dio_provider.dart';
import '../../../core/platform/device_timezone.dart';
import '../../../core/session/local_data_purge.dart';
import '../../../core/session/session_event_bus.dart';
import '../../../core/storage/secure_store.dart';
import '../../../core/sync/entity_ownership.dart';
import '../../consent/domain/consent.dart';
import '../data/fake_auth_repository.dart';
import '../data/http_auth_repository.dart';
import '../domain/auth_repository.dart';
import '../domain/session.dart';

final Provider<AuthRepository> authRepositoryProvider =
    Provider<AuthRepository>(
  (Ref ref) {
    final AppConfig config = ref.watch(appConfigProvider);
    if (config.useFakeBackend) {
      return FakeAuthRepository();
    }
    return HttpAuthRepository(
      ref.watch(apiClientProvider),
      ref.watch(tokenStoreProvider),
    );
  },
);

/// Base locale ouverte pour la session en cours.
///
/// Surcharge par `SessionController` au demarrage (la passphrase vient du
/// Keychain) et par les tests (`AppDatabase.inMemory()`).
final Provider<AppDatabase?> sessionDatabaseProvider =
    Provider<AppDatabase?>((Ref ref) => null);

final Provider<LocalDataPurge> localDataPurgeProvider =
    Provider<LocalDataPurge>(
  (Ref ref) => LocalDataPurge(
    secureStore: ref.watch(secureStoreProvider),
    keyProvider: ref.watch(databaseKeyProvider),
    tokenStore: ref.watch(tokenStoreProvider),
  ),
);

/// Etat de l'ecran d'authentification (distinct de la session elle-meme).
class AuthFormState {
  const AuthFormState({this.isSubmitting = false, this.error});

  final bool isSubmitting;
  final ApiError? error;

  AuthFormState copyWith(
      {bool? isSubmitting, ApiError? error, bool clearError = false}) {
    return AuthFormState(
      isSubmitting: isSubmitting ?? this.isSubmitting,
      error: clearError ? null : (error ?? this.error),
    );
  }
}

/// Source de verite de la session courante.
///
/// Le routeur ecoute ce notifier : toute redirection (login, consentement
/// bloquant, accueil) derive de [Session.stage], jamais d'un appel manuel a
/// `context.go()` disperse dans les ecrans.
class SessionController extends StateNotifier<Session> {
  SessionController({
    required AuthRepository repository,
    required DeviceTimezone timezone,
    required LocalDataPurge purge,
    required SessionEventBus eventBus,
    AppDatabase? Function()? databaseResolver,
  })  : _repository = repository,
        _timezone = timezone,
        _purge = purge,
        _databaseResolver = databaseResolver,
        super(const Session.unknown()) {
    _sessionEndSubscription = eventBus.sessionEnded.listen(_onSessionEnded);
  }

  final AuthRepository _repository;
  final DeviceTimezone _timezone;
  final LocalDataPurge _purge;
  final AppDatabase? Function()? _databaseResolver;
  StreamSubscription<SessionEndReason>? _sessionEndSubscription;

  /// Restaure la session au demarrage a froid.
  Future<void> restore() async {
    try {
      final Session session = await _repository.loadSession();
      state = session.withRecomputedStage();
    } on ApiError {
      // Jeton invalide ou serveur injoignable : on retombe sur l'ecran de
      // connexion plutot que de laisser l'app sur un splash infini.
      state = const Session.signedOut();
    }
  }

  Future<void> signIn({required String email, required String password}) async {
    final AuthResult result = await _repository.signIn(
      email: email,
      password: password,
      timezone: await _timezone.current(),
    );
    state = result.session.withRecomputedStage();
  }

  Future<void> signUp({
    required String email,
    required String password,
    required UserRole role,
    String? firstName,
  }) async {
    final AuthResult result = await _repository.signUp(
      email: email,
      password: password,
      role: role,
      firstName: firstName,
      timezone: await _timezone.current(),
    );
    state = result.session.withRecomputedStage();
  }

  /// Enregistre les choix de l'ecran de consentement.
  ///
  /// Tant que les trois finalites obligatoires ne sont pas accordees, l'etape
  /// reste [SessionStage.consentRequired] et le routeur maintient le blocage.
  Future<void> submitConsents(Map<ConsentPurpose, bool> choices) async {
    final ConsentState consents = await _repository.submitConsents(choices);
    state = state.copyWith(consents: consents).withRecomputedStage();
  }

  Future<void> revokeConsent(ConsentPurpose purpose) async {
    await _repository.revokeConsent(purpose);
    final ConsentState consents = await _repository.fetchConsents();
    state = state.copyWith(consents: consents).withRecomputedStage();
  }

  /// Resynchronise le fuseau si l'utilisateur a voyage.
  Future<void> refreshTimezone() async {
    final String current = await _timezone.current();
    if (current == state.timezone) {
      return;
    }
    try {
      await _repository.updateTimezone(current);
      state = state.copyWith(timezone: current);
    } on ApiError {
      // Sans consequence immediate : on retentera au prochain demarrage.
    }
  }

  /// Deconnexion : revocation serveur **puis purge locale complete**.
  Future<PurgeReport> signOut() async {
    try {
      await _repository.signOut();
    } on ApiError {
      // Voir HttpAuthRepository.signOut : la purge locale prime.
    }
    final PurgeReport report = await _purge.purge(
      database: _databaseResolver?.call(),
    );
    state = const Session.signedOut();
    return report;
  }

  Future<void> _onSessionEnded(SessionEndReason reason) async {
    if (reason == SessionEndReason.loggedOut) {
      return;
    }
    // Le refresh a ete refuse : la session est morte cote serveur. On purge
    // aussi en local, sinon la base de sante reste sur un appareil dont le
    // compte n'existe peut-etre plus.
    await _purge.purge(database: _databaseResolver?.call());
    state = const Session.signedOut();
  }

  @override
  void dispose() {
    unawaited(_sessionEndSubscription?.cancel());
    _sessionEndSubscription = null;
    super.dispose();
  }
}

final StateNotifierProvider<SessionController, Session> sessionProvider =
    StateNotifierProvider<SessionController, Session>((Ref ref) {
  return SessionController(
    repository: ref.watch(authRepositoryProvider),
    timezone: ref.watch(deviceTimezoneProvider),
    purge: ref.watch(localDataPurgeProvider),
    eventBus: ref.watch(sessionEventBusProvider),
    databaseResolver: () => ref.read(sessionDatabaseProvider),
  );
});
