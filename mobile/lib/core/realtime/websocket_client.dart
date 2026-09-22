import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../config/app_config.dart';
import '../network/connectivity_service.dart';
import '../network/dio_provider.dart';
import '../storage/secure_store.dart';
import '../sync/backoff.dart';
import 'realtime_event.dart';

enum RealtimeConnectionState { disconnected, connecting, connected }

/// Fabrique de canal, injectable pour tester la reconnexion sans vrai serveur.
typedef WebSocketChannelFactory = WebSocketChannel Function(Uri uri);

WebSocketChannel _defaultChannelFactory(Uri uri) =>
    WebSocketChannel.connect(uri);

/// Client WebSocket `/ws` avec reconnexion et backoff exponentiel.
///
/// Le temps reel est un **confort**, jamais une source de verite : si la
/// socket est morte, l'application continue de fonctionner sur la base locale
/// et la synchronisation REST. Une reconnexion echouee ne doit donc jamais
/// remonter une erreur bloquante a l'utilisateur.
class WebSocketClient {
  WebSocketClient({
    required AppConfig config,
    required TokenStore tokenStore,
    required ConnectivityService connectivity,
    WebSocketChannelFactory? channelFactory,
    ExponentialBackoff? backoff,
  })  : _config = config,
        _tokenStore = tokenStore,
        _connectivity = connectivity,
        _channelFactory = channelFactory ?? _defaultChannelFactory,
        _backoff = backoff ??
            ExponentialBackoff(
              initial: const Duration(seconds: 1),
              maxDelay: const Duration(seconds: 60),
            );

  final AppConfig _config;
  final TokenStore _tokenStore;
  final ConnectivityService _connectivity;
  final WebSocketChannelFactory _channelFactory;
  final ExponentialBackoff _backoff;

  final StreamController<RealtimeEvent> _events =
      StreamController<RealtimeEvent>.broadcast();
  final StreamController<RealtimeConnectionState> _states =
      StreamController<RealtimeConnectionState>.broadcast();

  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _channelSubscription;
  StreamSubscription<NetworkStatus>? _networkSubscription;
  Timer? _reconnectTimer;

  int _attempt = 0;
  bool _shouldStayConnected = false;
  RealtimeConnectionState _state = RealtimeConnectionState.disconnected;

  Stream<RealtimeEvent> get events => _events.stream;
  Stream<RealtimeConnectionState> get connectionState => _states.stream;
  RealtimeConnectionState get currentState => _state;
  int get reconnectAttempts => _attempt;

  Future<void> connect() async {
    _shouldStayConnected = true;
    _networkSubscription ??= _connectivity.changes.listen((NetworkStatus s) {
      if (s == NetworkStatus.online && _shouldStayConnected) {
        // Le reseau revient : on retente tout de suite plutot que d'attendre
        // la fin du backoff en cours.
        _attempt = 0;
        _reconnectTimer?.cancel();
        unawaited(_open());
      }
    });
    await _open();
  }

  Future<void> _open() async {
    if (!_shouldStayConnected || _state == RealtimeConnectionState.connecting) {
      return;
    }
    if (_connectivity.current == NetworkStatus.offline) {
      _setState(RealtimeConnectionState.disconnected);
      return;
    }

    final AuthTokens? tokens = await _tokenStore.read();
    if (tokens == null) {
      _setState(RealtimeConnectionState.disconnected);
      return;
    }

    _setState(RealtimeConnectionState.connecting);
    try {
      // Le JWT passe en query : les navigateurs et la plupart des proxys ne
      // permettent pas d'en-tete custom sur le handshake WebSocket.
      final Uri uri = Uri.parse(_config.webSocketUrl).replace(
        queryParameters: <String, String>{'token': tokens.accessToken},
      );
      final WebSocketChannel channel = _channelFactory(uri);
      _channel = channel;

      _channelSubscription = channel.stream.listen(
        _onFrame,
        onError: (Object _) => _scheduleReconnect(),
        onDone: _scheduleReconnect,
        cancelOnError: true,
      );

      _attempt = 0;
      _setState(RealtimeConnectionState.connected);
    } on Object {
      _scheduleReconnect();
    }
  }

  void _onFrame(dynamic frame) {
    final RealtimeEvent? event = RealtimeEvent.tryParse(frame);
    if (event != null && !_events.isClosed) {
      _events.add(event);
    }
  }

  void _scheduleReconnect() {
    _setState(RealtimeConnectionState.disconnected);
    unawaited(_closeChannel());
    if (!_shouldStayConnected) {
      return;
    }

    _attempt += 1;
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(_backoff.delayFor(_attempt), () {
      unawaited(_open());
    });
  }

  Future<void> _closeChannel() async {
    await _channelSubscription?.cancel();
    _channelSubscription = null;
    await _channel?.sink.close();
    _channel = null;
  }

  void send(Object? message) {
    _channel?.sink.add(message);
  }

  /// Ferme la connexion sans programmer de reconnexion (logout, mise en
  /// arriere-plan prolongee).
  Future<void> disconnect() async {
    _shouldStayConnected = false;
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    _attempt = 0;
    await _closeChannel();
    _setState(RealtimeConnectionState.disconnected);
  }

  void _setState(RealtimeConnectionState state) {
    if (_state == state) {
      return;
    }
    _state = state;
    if (!_states.isClosed) {
      _states.add(state);
    }
  }

  Future<void> dispose() async {
    await disconnect();
    await _networkSubscription?.cancel();
    _networkSubscription = null;
    await _events.close();
    await _states.close();
  }
}

final Provider<WebSocketClient> webSocketClientProvider =
    Provider<WebSocketClient>((Ref ref) {
  final WebSocketClient client = WebSocketClient(
    config: ref.watch(appConfigProvider),
    tokenStore: ref.watch(tokenStoreProvider),
    connectivity: ref.watch(connectivityServiceProvider),
  );
  ref.onDispose(client.dispose);
  return client;
});

final StreamProvider<RealtimeEvent> realtimeEventsProvider =
    StreamProvider<RealtimeEvent>(
  (Ref ref) => ref.watch(webSocketClientProvider).events,
);
