import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../network/auth_interceptor.dart';

/// Bus minimal permettant a la couche reseau de signaler « la session est
/// morte » sans dependre de la couche `features/auth` (ce qui creerait un
/// cycle : auth -> reseau -> auth).
class SessionEventBus {
  final StreamController<SessionEndReason> _controller =
      StreamController<SessionEndReason>.broadcast();

  Stream<SessionEndReason> get sessionEnded => _controller.stream;

  void notifySessionEnded(SessionEndReason reason) {
    if (!_controller.isClosed) {
      _controller.add(reason);
    }
  }

  Future<void> dispose() => _controller.close();
}

final Provider<SessionEventBus> sessionEventBusProvider =
    Provider<SessionEventBus>((Ref ref) {
  final SessionEventBus bus = SessionEventBus();
  ref.onDispose(bus.dispose);
  return bus;
});
