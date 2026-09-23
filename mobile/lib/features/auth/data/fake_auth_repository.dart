import '../../../core/error/api_error.dart';
import '../../../core/storage/secure_store.dart';
import '../../../core/sync/entity_ownership.dart';
import '../../consent/domain/consent.dart';
import '../domain/auth_repository.dart';
import '../domain/session.dart';

/// Source simulee, utilisee tant que l'API reelle n'est pas disponible et dans
/// les tests de widgets.
///
/// Elle reproduit fidelement les comportements que le socle doit savoir gerer :
/// - un compte neuf n'a **aucun** consentement, donc l'app doit se bloquer sur
///   l'ecran de consentement ;
/// - l'essai client dure 10 jours ;
/// - les consentements facultatifs sont a `false` par defaut.
class FakeAuthRepository implements AuthRepository {
  FakeAuthRepository({
    this.latency = Duration.zero,
    ConsentState? initialConsents,
    Session? initialSession,
  })  : _consents = initialConsents ?? const ConsentState.empty(),
        _session = initialSession;

  final Duration latency;
  ConsentState _consents;
  Session? _session;

  /// Force le prochain appel a echouer, pour tester les chemins d'erreur.
  ApiError? nextFailure;

  static const Duration trialDuration = Duration(days: 10);

  @override
  Future<AuthResult> signIn({
    required String email,
    required String password,
    required String timezone,
  }) async {
    await _tick();
    if (password.isEmpty) {
      throw const ApiError(
        code: ApiErrorCode.invalidCredentials,
        message: 'invalid_credentials',
        statusCode: 401,
        rawCode: 'INVALID_CREDENTIALS',
      );
    }
    final UserRole role =
        email.startsWith('coach') ? UserRole.coach : UserRole.client;
    return _buildResult(email: email, role: role, timezone: timezone);
  }

  @override
  Future<AuthResult> signUp({
    required String email,
    required String password,
    required UserRole role,
    required String timezone,
    String? firstName,
    String? lastName,
  }) async {
    await _tick();
    // Un compte neuf n'a accorde aucun consentement.
    _consents = const ConsentState.empty();
    return _buildResult(
      email: email,
      role: role,
      timezone: timezone,
      firstName: firstName,
    );
  }

  @override
  Future<Session> loadSession() async {
    await _tick();
    final Session? current = _session;
    if (current == null) {
      return const Session.signedOut();
    }
    return current.copyWith(consents: _consents).withRecomputedStage();
  }

  @override
  Future<void> updateTimezone(String timezone) async {
    await _tick();
    _session = _session?.copyWith(timezone: timezone);
  }

  @override
  Future<ConsentState> fetchConsents() async {
    await _tick();
    return _consents;
  }

  @override
  Future<ConsentState> submitConsents(Map<ConsentPurpose, bool> choices) async {
    await _tick();
    final DateTime now = DateTime.now().toUtc();
    ConsentState next = _consents;
    for (final ConsentPurpose purpose in ConsentPurpose.values) {
      final bool granted = choices[purpose] ?? false;
      next = next.withConsent(
        Consent(
          purpose: purpose,
          granted: granted,
          version: '1.0',
          grantedAt: granted ? now : null,
          revokedAt: granted ? null : now,
        ),
      );
    }
    _consents = next;
    _session = _session?.copyWith(consents: next).withRecomputedStage();
    return next;
  }

  @override
  Future<void> revokeConsent(ConsentPurpose purpose) async {
    await _tick();
    _consents = _consents.withConsent(
      Consent(
        purpose: purpose,
        granted: false,
        revokedAt: DateTime.now().toUtc(),
      ),
    );
    _session = _session?.copyWith(consents: _consents).withRecomputedStage();
  }

  @override
  Future<void> requestDataExport() => _tick();

  @override
  Future<void> requestAccountDeletion() => _tick();

  @override
  Future<void> signOut() async {
    await _tick();
    _session = null;
    _consents = const ConsentState.empty();
  }

  AuthResult _buildResult({
    required String email,
    required UserRole role,
    required String timezone,
    String? firstName,
  }) {
    final DateTime now = DateTime.now().toUtc();
    final Session session = Session(
      stage: SessionStage.unknown,
      userId: 'fake-${role.name}-${email.hashCode.abs()}',
      role: role,
      email: email,
      firstName: firstName,
      consents: _consents,
      subscriptionStatus:
          role == UserRole.client ? SubscriptionStatus.trialing : null,
      trialEndsAt: role == UserRole.client ? now.add(trialDuration) : null,
      coachingMode: CoachingMode.distance,
      timezone: timezone,
    ).withRecomputedStage();

    _session = session;
    return AuthResult(
      tokens: AuthTokens(
        accessToken: 'fake-access-${session.userId}',
        refreshToken: 'fake-refresh-${session.userId}',
        accessTokenExpiresAt: now.add(const Duration(minutes: 15)),
      ),
      session: session,
    );
  }

  Future<void> _tick() async {
    final ApiError? failure = nextFailure;
    if (failure != null) {
      nextFailure = null;
      throw failure;
    }
    if (latency > Duration.zero) {
      await Future<void>.delayed(latency);
    }
  }
}
