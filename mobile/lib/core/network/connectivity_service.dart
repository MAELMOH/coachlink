import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Etat reseau de l'appareil.
///
/// Attention : `online` signifie « une interface reseau est disponible », pas
/// « l'API repond ». La file de synchronisation ne doit jamais considerer une
/// operation comme perdue sur la seule foi de ce signal.
enum NetworkStatus { online, offline }

/// Abstraction substituable : les tests d'integration doivent pouvoir simuler
/// la perte puis le retour du reseau sans toucher au vrai appareil.
abstract class ConnectivityService {
  NetworkStatus get current;
  Stream<NetworkStatus> get changes;
  Future<void> dispose();
}

class PlatformConnectivityService implements ConnectivityService {
  PlatformConnectivityService([Connectivity? connectivity])
      : _connectivity = connectivity ?? Connectivity() {
    _subscription = _connectivity.onConnectivityChanged.listen(
      (List<ConnectivityResult> results) => _emit(_statusOf(results)),
    );
    unawaited(_primeInitialStatus());
  }

  final Connectivity _connectivity;
  final StreamController<NetworkStatus> _controller =
      StreamController<NetworkStatus>.broadcast();
  StreamSubscription<List<ConnectivityResult>>? _subscription;

  NetworkStatus _current = NetworkStatus.online;

  @override
  NetworkStatus get current => _current;

  @override
  Stream<NetworkStatus> get changes => _controller.stream;

  Future<void> _primeInitialStatus() async {
    try {
      _emit(_statusOf(await _connectivity.checkConnectivity()));
    } on Object {
      // Plateforme sans plugin (tests headless) : on reste optimiste, la
      // couche reseau detectera l'echec reel.
      _emit(NetworkStatus.online);
    }
  }

  void _emit(NetworkStatus status) {
    if (status == _current) {
      return;
    }
    _current = status;
    if (!_controller.isClosed) {
      _controller.add(status);
    }
  }

  static NetworkStatus _statusOf(List<ConnectivityResult> results) {
    final bool offline = results.isEmpty ||
        results.every((ConnectivityResult r) => r == ConnectivityResult.none);
    return offline ? NetworkStatus.offline : NetworkStatus.online;
  }

  @override
  Future<void> dispose() async {
    await _subscription?.cancel();
    _subscription = null;
    await _controller.close();
  }
}

/// Connectivite pilotable a la main, pour les tests.
class FakeConnectivityService implements ConnectivityService {
  FakeConnectivityService([this._current = NetworkStatus.online]);

  NetworkStatus _current;
  final StreamController<NetworkStatus> _controller =
      StreamController<NetworkStatus>.broadcast();

  @override
  NetworkStatus get current => _current;

  @override
  Stream<NetworkStatus> get changes => _controller.stream;

  void set(NetworkStatus status) {
    if (status == _current) {
      return;
    }
    _current = status;
    _controller.add(status);
  }

  void goOffline() => set(NetworkStatus.offline);
  void goOnline() => set(NetworkStatus.online);

  @override
  Future<void> dispose() => _controller.close();
}

final Provider<ConnectivityService> connectivityServiceProvider =
    Provider<ConnectivityService>((Ref ref) {
  final PlatformConnectivityService service = PlatformConnectivityService();
  ref.onDispose(service.dispose);
  return service;
});

final StreamProvider<NetworkStatus> networkStatusProvider =
    StreamProvider<NetworkStatus>((Ref ref) {
  final ConnectivityService service = ref.watch(connectivityServiceProvider);
  return service.changes;
});
