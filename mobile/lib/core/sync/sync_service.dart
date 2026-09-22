import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../error/api_error.dart';
import '../network/api_client.dart';
import '../network/connectivity_service.dart';
import '../network/dio_provider.dart';
import 'backoff.dart';
import 'pending_operation.dart';
import 'sync_queue.dart';
import 'sync_status.dart';

/// Applique les deltas recus de `GET /sync?since=` a la base locale.
///
/// Implemente par la couche `features` (chaque repository sait ecrire ses
/// propres tables). Le socle n'a pas a connaitre les entites metier.
abstract class SyncDeltaApplier {
  /// Retourne l'horodatage le plus recent applique, ou `null` si rien.
  Future<DateTime?> apply(Map<String, Object?> delta);
}

class NoopSyncDeltaApplier implements SyncDeltaApplier {
  const NoopSyncDeltaApplier();

  @override
  Future<DateTime?> apply(Map<String, Object?> delta) async => null;
}

/// Orchestre la file d'ecritures offline et le rapatriement des deltas.
///
/// Garanties :
/// - **Rien n'est perdu** : une ecriture est d'abord persistee en file, puis
///   envoyee. Si l'app est tuee entre les deux, la file la rejouera.
/// - **Rien n'est duplique** : chaque operation porte son `Idempotency-Key`
///   persistee, reutilisee a l'identique a chaque rejeu.
/// - **Un seul drain a la fois** : deux drains concurrents enverraient la meme
///   operation deux fois.
class SyncService {
  SyncService({
    required SyncQueue queue,
    required ApiClient api,
    required ConnectivityService connectivity,
    SyncDeltaApplier applier = const NoopSyncDeltaApplier(),
    ExponentialBackoff? backoff,
    DateTime Function()? clock,
  })  : _queue = queue,
        _api = api,
        _connectivity = connectivity,
        _applier = applier,
        _backoff = backoff ?? ExponentialBackoff(),
        _now = clock ?? (() => DateTime.now().toUtc()) {
    _connectivitySubscription = _connectivity.changes.listen(_onNetworkChange);
  }

  final SyncQueue _queue;
  final ApiClient _api;
  final ConnectivityService _connectivity;
  final SyncDeltaApplier _applier;
  final ExponentialBackoff _backoff;
  final DateTime Function() _now;

  StreamSubscription<NetworkStatus>? _connectivitySubscription;
  Future<void>? _inFlightDrain;

  final StreamController<SyncStatus> _statusController =
      StreamController<SyncStatus>.broadcast();

  SyncStatus _status = const SyncStatus();

  SyncStatus get status => _status;
  Stream<SyncStatus> get statusChanges => _statusController.stream;

  /// Enfile une ecriture puis tente de l'envoyer immediatement.
  ///
  /// L'appelant ne doit **pas** attendre le reseau : la persistance locale est
  /// faite avant le retour, l'envoi est opportuniste.
  Future<PendingOperation> enqueue(PendingOperation operation) async {
    final PendingOperation stored = await _queue.enqueue(operation);
    await _refreshCounters();
    unawaited(drain());
    return stored;
  }

  /// Vide la file. Sans effet si un drain est deja en cours (single-flight).
  Future<void> drain() {
    final Future<void>? pending = _inFlightDrain;
    if (pending != null) {
      return pending;
    }
    final Future<void> future = _drain();
    _inFlightDrain = future;
    return future.whenComplete(() => _inFlightDrain = null);
  }

  Future<void> _drain() async {
    if (_connectivity.current == NetworkStatus.offline) {
      await _refreshCounters(phase: SyncPhase.offline);
      return;
    }

    final List<PendingOperation> due = await _queue.dueOperations(_now());
    if (due.isEmpty) {
      await _refreshCounters(phase: SyncPhase.idle);
      return;
    }

    _emit(_status.copyWith(phase: SyncPhase.syncing, clearError: true));

    for (final PendingOperation operation in due) {
      final bool keepGoing = await _send(operation);
      if (!keepGoing) {
        // Reseau tombe en cours de route : inutile d'insister sur les
        // suivantes, et surtout on preserve l'ordre FIFO.
        await _refreshCounters(phase: SyncPhase.offline);
        return;
      }
    }

    await _refreshCounters(phase: SyncPhase.idle);
  }

  /// Retourne `false` si le drain doit s'interrompre (reseau indisponible).
  Future<bool> _send(PendingOperation operation) async {
    try {
      switch (operation.method.toUpperCase()) {
        case 'POST':
          await _api.post(
            operation.path,
            body: operation.payload,
            idempotencyKey: operation.idempotencyKey,
          );
        case 'PATCH':
          await _api.patch(
            operation.path,
            body: operation.payload,
            idempotencyKey: operation.idempotencyKey,
          );
        case 'DELETE':
          await _api.delete(
            operation.path,
            idempotencyKey: operation.idempotencyKey,
          );
        default:
          throw ApiError(
            code: ApiErrorCode.unknown,
            message: 'unsupported_method_${operation.method}',
            rawCode: 'UNSUPPORTED_METHOD',
          );
      }
      await _queue.markSucceeded(operation.id);
      return true;
    } on ApiError catch (error) {
      return _handleFailure(operation, error);
    }
  }

  Future<bool> _handleFailure(
    PendingOperation operation,
    ApiError error,
  ) async {
    // Le consentement manquant n'est pas une erreur de donnee : l'operation
    // doit survivre et repartir une fois le consentement accorde.
    final bool blockedByConsent = error.code == ApiErrorCode.consentRequired;

    if (error.isRetryable || blockedByConsent) {
      final int attempt = operation.attempts + 1;
      if (attempt >= PendingOperation.maxAttempts && !blockedByConsent) {
        await _queue.markDead(operation.id, error: error);
      } else {
        await _queue.markRetryable(
          operation.id,
          error: error,
          nextAttempt: _backoff.nextAttemptAt(attempt, from: _now()),
        );
      }
      await _refreshCounters(
        phase: error.isNetworkFailure ? SyncPhase.offline : SyncPhase.error,
        error: error,
      );
      return !error.isNetworkFailure;
    }

    if (error.isPermanentClientFailure) {
      // Rejouer a l'identique ne changera rien : on sort l'operation du cycle
      // plutot que de bloquer indefiniment la file derriere elle.
      await _queue.markDead(operation.id, error: error);
      await _refreshCounters(phase: SyncPhase.error, error: error);
      return true;
    }

    await _queue.markRetryable(
      operation.id,
      error: error,
      nextAttempt: _backoff.nextAttemptAt(operation.attempts + 1, from: _now()),
    );
    await _refreshCounters(phase: SyncPhase.error, error: error);
    return true;
  }

  /// Rapatrie les deltas serveur depuis [since].
  ///
  /// Toujours appele **apres** le drain : on pousse ses propres ecritures avant
  /// de tirer celles des autres, pour ne pas se faire ecraser par une version
  /// serveur qui ignore encore nos modifications locales.
  Future<DateTime?> pull({DateTime? since}) async {
    if (_connectivity.current == NetworkStatus.offline) {
      await _refreshCounters(phase: SyncPhase.offline);
      return null;
    }
    _emit(_status.copyWith(phase: SyncPhase.syncing, clearError: true));
    try {
      final Map<String, Object?> delta = await _api.get(
        '/sync',
        query: <String, Object?>{
          if (since != null) 'since': since.toUtc().toIso8601String(),
        },
      );
      final DateTime? appliedUntil = await _applier.apply(delta);
      await _refreshCounters(
        phase: SyncPhase.idle,
        lastSyncedAt: appliedUntil ?? _now(),
      );
      return appliedUntil;
    } on ApiError catch (error) {
      await _refreshCounters(
        phase: error.isNetworkFailure ? SyncPhase.offline : SyncPhase.error,
        error: error,
      );
      return null;
    }
  }

  /// Cycle complet : pousser puis tirer.
  Future<void> synchronize({DateTime? since}) async {
    await drain();
    await pull(since: since);
  }

  void _onNetworkChange(NetworkStatus status) {
    if (status == NetworkStatus.online) {
      unawaited(drain());
    } else {
      _emit(_status.copyWith(phase: SyncPhase.offline));
    }
  }

  Future<void> _refreshCounters({
    SyncPhase? phase,
    ApiError? error,
    DateTime? lastSyncedAt,
  }) async {
    final int pending = await _queue.pendingCount();
    final int dead = await _queue.deadCount();
    _emit(
      _status.copyWith(
        phase: phase,
        pendingCount: pending,
        deadCount: dead,
        lastError: error,
        clearError: error == null && phase == SyncPhase.idle,
        lastSyncedAt: lastSyncedAt,
      ),
    );
  }

  void _emit(SyncStatus status) {
    _status = status;
    if (!_statusController.isClosed) {
      _statusController.add(status);
    }
  }

  Future<void> dispose() async {
    await _connectivitySubscription?.cancel();
    _connectivitySubscription = null;
    await _statusController.close();
  }
}

/// La file reelle est branchee sur la base Drift, qui n'existe qu'une fois
/// l'utilisateur authentifie (la cle de chiffrement vient du Keychain).
/// Ce provider est donc surcharge au demarrage de la session.
final Provider<SyncQueue> syncQueueProvider = Provider<SyncQueue>((Ref ref) {
  throw UnimplementedError(
    'syncQueueProvider doit etre surcharge une fois la base locale ouverte '
    '(voir SessionBootstrap) ou par un InMemorySyncQueue dans les tests.',
  );
});

final Provider<SyncService> syncServiceProvider = Provider<SyncService>(
  (Ref ref) {
    final SyncService service = SyncService(
      queue: ref.watch(syncQueueProvider),
      api: ref.watch(apiClientProvider),
      connectivity: ref.watch(connectivityServiceProvider),
    );
    ref.onDispose(service.dispose);
    return service;
  },
);

/// Etat de synchronisation observable par l'UI **et** par les tests.
final StreamProvider<SyncStatus> syncStatusProvider =
    StreamProvider<SyncStatus>((Ref ref) {
  final SyncService service = ref.watch(syncServiceProvider);
  return service.statusChanges;
});
