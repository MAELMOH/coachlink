import '../../../core/network/api_client.dart';
import '../../../core/network/dio_provider.dart';
import '../../../core/storage/secure_store.dart';
import '../../../core/sync/entity_ownership.dart';
import '../../consent/domain/consent.dart';
import '../domain/auth_repository.dart';
import '../domain/session.dart';

/// Implementation branchee sur l'API (ARCHITECTURE.md 8).
///
/// Les chemins suivent le backlog Phase 2.2 / 2.7. Ils seront reconfirmes
/// contre l'OpenAPI des que `back` l'expose.
class HttpAuthRepository implements AuthRepository {
  const HttpAuthRepository(this._api, this._tokenStore);

  final ApiClient _api;
  final TokenStore _tokenStore;

  @override
  Future<AuthResult> signIn({
    required String email,
    required String password,
    required String timezone,
  }) async {
    final Map<String, Object?> body = await _api.post(
      '/auth/login',
      body: <String, Object?>{
        'email': email,
        'password': password,
        'timezone': timezone,
      },
      anonymous: true,
    );
    return _consume(body);
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
    final Map<String, Object?> body = await _api.post(
      '/auth/register',
      body: <String, Object?>{
        'email': email,
        'password': password,
        'role': role.name,
        'timezone': timezone,
        if (firstName != null) 'first_name': firstName,
        if (lastName != null) 'last_name': lastName,
      },
      anonymous: true,
    );
    return _consume(body);
  }

  @override
  Future<Session> loadSession() async {
    final Map<String, Object?> body = await _api.get('/me');
    return parseSession(body);
  }

  @override
  Future<void> updateTimezone(String timezone) async {
    await _api.patch('/me', body: <String, Object?>{'timezone': timezone});
  }

  @override
  Future<ConsentState> fetchConsents() async {
    final List<Map<String, Object?>> items = await _api.getList('/me/consents');
    return ConsentState.fromJsonList(items);
  }

  @override
  Future<ConsentState> submitConsents(
    Map<ConsentPurpose, bool> choices,
  ) async {
    // On envoie TOUTES les finalites, y compris celles refusees : cote RGPD,
    // « non coche » doit etre journalise comme un refus explicite et date,
    // pas comme une absence de reponse.
    final List<Map<String, Object?>> payload = ConsentPurpose.values
        .map(
          (ConsentPurpose purpose) => <String, Object?>{
            'purpose': purpose.wireValue,
            'granted': choices[purpose] ?? false,
          },
        )
        .toList(growable: false);

    final Map<String, Object?> body = await _api.post(
      '/me/consents',
      body: <String, Object?>{'consents': payload},
    );
    final Object? items = body['items'] ?? body['consents'];
    if (items is List) {
      return ConsentState.fromJsonList(
        items
            .whereType<Map<Object?, Object?>>()
            .map(Map<String, Object?>.from)
            .toList(growable: false),
      );
    }
    return fetchConsents();
  }

  @override
  Future<void> revokeConsent(ConsentPurpose purpose) async {
    await _api.post(
      '/me/consents',
      body: <String, Object?>{
        'consents': <Map<String, Object?>>[
          <String, Object?>{'purpose': purpose.wireValue, 'granted': false},
        ],
      },
    );
  }

  @override
  Future<void> requestDataExport() async {
    await _api.post('/me/data-export');
  }

  @override
  Future<void> requestAccountDeletion() async {
    await _api.post('/me/delete-account');
  }

  @override
  Future<void> signOut() async {
    try {
      await _api.post('/auth/logout');
    } on Object {
      // Un logout qui echoue cote reseau ne doit jamais empecher la purge
      // locale : mieux vaut un refresh token encore vivant cote serveur
      // qu'une base de donnees de sante laissee sur l'appareil.
    }
    await _tokenStore.clear();
  }

  Future<AuthResult> _consume(Map<String, Object?> body) async {
    final AuthTokens tokens = HttpTokenRefresher.parseTokens(body);
    await _tokenStore.save(tokens);

    final Object? user = body['user'] ?? body['me'];
    final Session session = user is Map
        ? parseSession(Map<String, Object?>.from(user))
        : await loadSession();
    return AuthResult(tokens: tokens, session: session);
  }

  /// Mappe la reponse `/me` vers [Session].
  static Session parseSession(Map<String, Object?> json) {
    final Object? rawConsents = json['consents'];
    final ConsentState consents = rawConsents is List
        ? ConsentState.fromJsonList(
            rawConsents
                .whereType<Map<Object?, Object?>>()
                .map(Map<String, Object?>.from)
                .toList(growable: false),
          )
        : const ConsentState.empty();

    final Object? subscription = json['subscription'];
    final Map<String, Object?> sub = subscription is Map
        ? Map<String, Object?>.from(subscription)
        : const <String, Object?>{};

    final Object? link = json['active_link'] ?? json['coach_client_link'];
    final Map<String, Object?> linkMap = link is Map
        ? Map<String, Object?>.from(link)
        : const <String, Object?>{};

    return Session(
      stage: SessionStage.unknown,
      userId: json['id'] as String?,
      role: UserRole.fromWire(json['role'] as String?),
      email: json['email'] as String?,
      firstName: json['first_name'] as String?,
      coachingMode: CoachingMode.fromWire(
        (linkMap['coaching_mode'] ?? json['default_coaching_mode']) as String?,
      ),
      consents: consents,
      subscriptionStatus: SubscriptionStatus.fromWire(sub['status'] as String?),
      trialEndsAt: _parseDate(sub['trial_ends_at'] ?? json['trial_ends_at']),
      offersNutrition: json['offers_nutrition'] == true,
      timezone: json['timezone'] as String?,
    ).withRecomputedStage();
  }

  static DateTime? _parseDate(Object? value) =>
      value is String ? DateTime.tryParse(value)?.toUtc() : null;
}
