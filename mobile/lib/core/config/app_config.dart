import 'package:flutter/foundation.dart';

/// Environnement d'execution, pilote par `--dart-define=COACHLINK_ENV=...`.
enum AppEnvironment { dev, staging, prod }

/// Configuration injectee au build. **Aucune valeur secrete ne doit vivre ici**
/// ni dans le repo : les empreintes de certificat et l'URL d'API sont fournies
/// par `--dart-define` (ou `--dart-define-from-file`) au moment du build CI.
///
/// Exemple :
/// ```
/// flutter build apk \
///   --dart-define=COACHLINK_ENV=prod \
///   --dart-define=COACHLINK_API_BASE_URL=https://api.example.tld/api/v1 \
///   --dart-define=COACHLINK_SPKI_PINS=sha256/AAAA...=,sha256/BBBB...=
/// ```
@immutable
class AppConfig {
  const AppConfig({
    required this.environment,
    required this.apiBaseUrl,
    required this.webSocketUrl,
    required this.deepLinkHost,
    required this.spkiPins,
    required this.connectTimeout,
    required this.receiveTimeout,
    this.useFakeBackend = false,
  });

  /// Construit la configuration depuis les `--dart-define`.
  factory AppConfig.fromEnvironment() {
    const envName = String.fromEnvironment(
      'COACHLINK_ENV',
      defaultValue: 'dev',
    );
    final environment = AppEnvironment.values.firstWhere(
      (AppEnvironment e) => e.name == envName,
      orElse: () => AppEnvironment.dev,
    );

    const apiBaseUrl = String.fromEnvironment(
      'COACHLINK_API_BASE_URL',
      defaultValue: 'http://10.0.2.2:8000/api/v1',
    );
    const wsUrl = String.fromEnvironment('COACHLINK_WS_URL');
    const deepLinkHost = String.fromEnvironment(
      'COACHLINK_DEEPLINK_HOST',
      // Nom de domaine encore provisoire (valide par le Tech Lead le 2026-09-22) :
      // il n'est volontairement pas fige ailleurs que dans cette valeur par defaut.
      defaultValue: 'coachlink.app',
    );
    const rawPins = String.fromEnvironment('COACHLINK_SPKI_PINS');

    // Sources simulees tant que `back` n'expose pas son OpenAPI. Par defaut
    // actif en dev uniquement : un build staging/prod qui tomberait sur des
    // donnees factices serait un incident, pas une commodite.
    const fakeBackend = bool.fromEnvironment(
      'COACHLINK_FAKE_API',
      defaultValue: true,
    );

    return AppConfig(
      environment: environment,
      useFakeBackend: fakeBackend && environment == AppEnvironment.dev,
      apiBaseUrl: apiBaseUrl,
      webSocketUrl: wsUrl.isNotEmpty ? wsUrl : _deriveWsUrl(apiBaseUrl),
      deepLinkHost: deepLinkHost,
      spkiPins: _parsePins(rawPins),
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 20),
    );
  }

  final AppEnvironment environment;
  final String apiBaseUrl;
  final String webSocketUrl;

  /// Hote des App Links / Universal Links, ex. `coachlink.app`.
  /// Lien d'invitation : `https://<deepLinkHost>/invite/<code>`.
  /// Fallback custom scheme : `coachlink://invite/<code>`.
  final String deepLinkHost;

  /// Empreintes SPKI SHA-256 acceptees, au format `sha256/<base64>`.
  ///
  /// Vide = pinning desactive (cas du dev local et des tests).
  final List<String> spkiPins;

  final Duration connectTimeout;
  final Duration receiveTimeout;

  /// Bascule sur les repositories simules (`Fake*Repository`).
  final bool useFakeBackend;

  bool get isProduction => environment == AppEnvironment.prod;

  /// Le pinning n'est applique qu'en release **et** si des empreintes existent.
  /// Le desactiver en debug permet de brancher un proxy de debug local.
  bool get isPinningEnabled => kReleaseMode && spkiPins.isNotEmpty;

  /// Schema custom de repli quand les App Links ne sont pas resolus.
  static const String customScheme = 'coachlink';

  String invitationLink(String code) => 'https://$deepLinkHost/invite/$code';

  static List<String> _parsePins(String raw) => raw
      .split(',')
      .map((String p) => p.trim())
      .where((String p) => p.isNotEmpty)
      .toList(growable: false);

  static String _deriveWsUrl(String apiBaseUrl) {
    final uri = Uri.parse(apiBaseUrl);
    final scheme = uri.scheme == 'https' ? 'wss' : 'ws';
    return uri.replace(scheme: scheme, path: '/ws', query: '').toString();
  }

  AppConfig copyWith({
    AppEnvironment? environment,
    String? apiBaseUrl,
    String? webSocketUrl,
    String? deepLinkHost,
    List<String>? spkiPins,
    Duration? connectTimeout,
    Duration? receiveTimeout,
    bool? useFakeBackend,
  }) {
    return AppConfig(
      environment: environment ?? this.environment,
      apiBaseUrl: apiBaseUrl ?? this.apiBaseUrl,
      webSocketUrl: webSocketUrl ?? this.webSocketUrl,
      deepLinkHost: deepLinkHost ?? this.deepLinkHost,
      spkiPins: spkiPins ?? this.spkiPins,
      connectTimeout: connectTimeout ?? this.connectTimeout,
      receiveTimeout: receiveTimeout ?? this.receiveTimeout,
      useFakeBackend: useFakeBackend ?? this.useFakeBackend,
    );
  }
}
