import 'dart:async';

import 'package:drift/drift.dart';

import '../database/app_database.dart';
import '../error/api_error.dart';
import 'entity_ownership.dart';
import 'pending_operation.dart';

/// File d'ecritures offline.
///
/// Contrat : FIFO strict par `sequence`. Une operation `update` sur une entite
/// creee hors ligne doit partir **apres** son `create`, sinon le serveur reçoit
/// une mise a jour sur un identifiant qu'il ne connait pas.
abstract class SyncQueue {
  Future<PendingOperation> enqueue(PendingOperation operation);

  /// Operations pretes a etre envoyees, dans l'ordre d'enfilement.
  Future<List<PendingOperation>> dueOperations(DateTime now, {int limit = 50});

  Future<void> markSucceeded(String operationId);

  /// Echec temporaire : l'operation reste en file, reprogrammee a [nextAttempt].
  Future<void> markRetryable(
    String operationId, {
    required ApiError error,
    required DateTime nextAttempt,
  });

  /// Echec definitif : l'operation sort du cycle de rejeu mais reste stockee
  /// pour pouvoir etre montree a l'utilisateur et diagnostiquee.
  Future<void> markDead(String operationId, {required ApiError error});

  Future<int> pendingCount();
  Future<int> deadCount();
  Stream<int> watchPendingCount();
  Future<List<PendingOperation>> deadOperations();
  Future<void> clear();
}

class DriftSyncQueue implements SyncQueue {
  DriftSyncQueue(this._db);

  final AppDatabase _db;

  @override
  Future<PendingOperation> enqueue(PendingOperation operation) async {
    final int sequence =
        await _db.into(_db.pendingOperations).insert(_toCompanion(operation));
    return operation.copyWith(sequence: sequence);
  }

  @override
  Future<List<PendingOperation>> dueOperations(
    DateTime now, {
    int limit = 50,
  }) async {
    final List<PendingOperationData> rows =
        await (_db.select(_db.pendingOperations)
              ..where((PendingOperations t) => t.isDead.equals(false))
              ..where(
                (PendingOperations t) =>
                    t.nextAttemptAt.isNull() |
                    t.nextAttemptAt.isSmallerOrEqualValue(now),
              )
              ..orderBy(<OrderClauseGenerator<PendingOperations>>[
                (PendingOperations t) => OrderingTerm.asc(t.sequence),
              ])
              ..limit(limit))
            .get();
    return rows.map(_fromRow).toList(growable: false);
  }

  @override
  Future<void> markSucceeded(String operationId) async {
    await (_db.delete(_db.pendingOperations)
          ..where((PendingOperations t) => t.id.equals(operationId)))
        .go();
  }

  @override
  Future<void> markRetryable(
    String operationId, {
    required ApiError error,
    required DateTime nextAttempt,
  }) async {
    await _db.customUpdate(
      'UPDATE pending_operations SET attempts = attempts + 1, '
      'next_attempt_at = ?, last_error_code = ?, last_error_message = ? '
      'WHERE id = ?',
      variables: <Variable<Object>>[
        Variable<DateTime>(nextAttempt),
        Variable<String>(error.rawCode ?? error.code.wireValue),
        Variable<String>(error.message),
        Variable<String>(operationId),
      ],
      updates: <TableInfo<Table, Object?>>{_db.pendingOperations},
    );
  }

  @override
  Future<void> markDead(String operationId, {required ApiError error}) async {
    await (_db.update(_db.pendingOperations)
          ..where((PendingOperations t) => t.id.equals(operationId)))
        .write(
      PendingOperationsCompanion(
        isDead: const Value<bool>(true),
        lastErrorCode: Value<String>(error.rawCode ?? error.code.wireValue),
        lastErrorMessage: Value<String>(error.message),
      ),
    );
  }

  @override
  Future<int> pendingCount() async {
    final Expression<int> count = _db.pendingOperations.id.count();
    final JoinedSelectStatement<HasResultSet, dynamic> query =
        _db.selectOnly(_db.pendingOperations)
          ..addColumns(<Expression<Object>>[count])
          ..where(_db.pendingOperations.isDead.equals(false));
    final TypedResult row = await query.getSingle();
    return row.read(count) ?? 0;
  }

  @override
  Future<int> deadCount() async {
    final Expression<int> count = _db.pendingOperations.id.count();
    final JoinedSelectStatement<HasResultSet, dynamic> query =
        _db.selectOnly(_db.pendingOperations)
          ..addColumns(<Expression<Object>>[count])
          ..where(_db.pendingOperations.isDead.equals(true));
    final TypedResult row = await query.getSingle();
    return row.read(count) ?? 0;
  }

  @override
  Stream<int> watchPendingCount() {
    return (_db.select(_db.pendingOperations)
          ..where((PendingOperations t) => t.isDead.equals(false)))
        .watch()
        .map((List<PendingOperationData> rows) => rows.length);
  }

  @override
  Future<List<PendingOperation>> deadOperations() async {
    final List<PendingOperationData> rows =
        await (_db.select(_db.pendingOperations)
              ..where((PendingOperations t) => t.isDead.equals(true))
              ..orderBy(<OrderClauseGenerator<PendingOperations>>[
                (PendingOperations t) => OrderingTerm.asc(t.sequence),
              ]))
            .get();
    return rows.map(_fromRow).toList(growable: false);
  }

  @override
  Future<void> clear() async {
    await _db.delete(_db.pendingOperations).go();
  }

  PendingOperationsCompanion _toCompanion(PendingOperation op) {
    return PendingOperationsCompanion.insert(
      id: op.id,
      entityType: op.entityType.wireValue,
      entityId: op.entityId,
      operation: op.kind.name,
      method: op.method,
      path: op.path,
      payload: op.payloadJson,
      idempotencyKey: op.idempotencyKey,
      createdAt: op.createdAt,
      attempts: Value<int>(op.attempts),
      nextAttemptAt: Value<DateTime?>(op.nextAttemptAt),
    );
  }

  PendingOperation _fromRow(PendingOperationData row) {
    return PendingOperation(
      id: row.id,
      entityType:
          SyncEntityType.fromWire(row.entityType) ?? SyncEntityType.userProfile,
      entityId: row.entityId,
      kind: SyncOperationKind.fromWire(row.operation),
      method: row.method,
      path: row.path,
      payload: PendingOperation.decodePayload(row.payload),
      idempotencyKey: row.idempotencyKey,
      sequence: row.sequence,
      attempts: row.attempts,
      createdAt: row.createdAt,
      nextAttemptAt: row.nextAttemptAt,
      lastErrorCode: row.lastErrorCode,
      lastErrorMessage: row.lastErrorMessage,
      isDead: row.isDead,
    );
  }
}

/// File en memoire : permet de tester toute la logique de synchronisation
/// (ordre FIFO, rejeu, backoff, idempotence) sans SQLite ni Keychain.
class InMemorySyncQueue implements SyncQueue {
  final List<PendingOperation> _operations = <PendingOperation>[];
  final StreamController<int> _pendingCount = StreamController<int>.broadcast();
  int _sequence = 0;

  List<PendingOperation> get snapshot =>
      List<PendingOperation>.unmodifiable(_operations);

  @override
  Future<PendingOperation> enqueue(PendingOperation operation) async {
    final PendingOperation stored = operation.copyWith(sequence: ++_sequence);
    _operations.add(stored);
    _emit();
    return stored;
  }

  @override
  Future<List<PendingOperation>> dueOperations(
    DateTime now, {
    int limit = 50,
  }) async {
    final List<PendingOperation> due =
        _operations.where((PendingOperation op) => op.isDue(now)).toList()
          ..sort(
            (PendingOperation a, PendingOperation b) =>
                a.sequence.compareTo(b.sequence),
          );
    return due.take(limit).toList(growable: false);
  }

  @override
  Future<void> markSucceeded(String operationId) async {
    _operations.removeWhere((PendingOperation op) => op.id == operationId);
    _emit();
  }

  @override
  Future<void> markRetryable(
    String operationId, {
    required ApiError error,
    required DateTime nextAttempt,
  }) async {
    _update(
      operationId,
      (PendingOperation op) => op.copyWith(
        attempts: op.attempts + 1,
        nextAttemptAt: nextAttempt,
        lastErrorCode: error.rawCode ?? error.code.wireValue,
        lastErrorMessage: error.message,
      ),
    );
  }

  @override
  Future<void> markDead(String operationId, {required ApiError error}) async {
    _update(
      operationId,
      (PendingOperation op) => op.copyWith(
        isDead: true,
        attempts: op.attempts + 1,
        lastErrorCode: error.rawCode ?? error.code.wireValue,
        lastErrorMessage: error.message,
      ),
    );
    _emit();
  }

  @override
  Future<int> pendingCount() async =>
      _operations.where((PendingOperation op) => !op.isDead).length;

  @override
  Future<int> deadCount() async =>
      _operations.where((PendingOperation op) => op.isDead).length;

  @override
  Stream<int> watchPendingCount() => _pendingCount.stream;

  @override
  Future<List<PendingOperation>> deadOperations() async =>
      _operations.where((PendingOperation op) => op.isDead).toList();

  @override
  Future<void> clear() async {
    _operations.clear();
    _emit();
  }

  Future<void> dispose() => _pendingCount.close();

  void _update(
    String id,
    PendingOperation Function(PendingOperation) transform,
  ) {
    final int index =
        _operations.indexWhere((PendingOperation op) => op.id == id);
    if (index >= 0) {
      _operations[index] = transform(_operations[index]);
    }
  }

  void _emit() {
    if (!_pendingCount.isClosed) {
      _pendingCount
          .add(_operations.where((PendingOperation op) => !op.isDead).length);
    }
  }
}
