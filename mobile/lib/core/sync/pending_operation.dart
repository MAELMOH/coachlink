import 'dart:convert';

import 'package:uuid/uuid.dart';

import 'entity_ownership.dart';

const Uuid _uuid = Uuid();

enum SyncOperationKind {
  create,
  update,
  delete;

  static SyncOperationKind fromWire(String value) => SyncOperationKind.values
      .firstWhere((SyncOperationKind k) => k.name == value);
}

/// Operation d'ecriture en attente d'envoi au serveur.
///
/// Modele Dart pur (aucune dependance a Drift) : la logique de file est
/// testable sans base de donnees.
class PendingOperation {
  PendingOperation({
    required this.id,
    required this.entityType,
    required this.entityId,
    required this.kind,
    required this.method,
    required this.path,
    required this.payload,
    required this.idempotencyKey,
    required this.createdAt,
    this.sequence = 0,
    this.attempts = 0,
    this.nextAttemptAt,
    this.lastErrorCode,
    this.lastErrorMessage,
    this.isDead = false,
  });

  /// Cree une operation prete a enfiler.
  ///
  /// **L'`Idempotency-Key` est generee ici, une seule fois, et persistee avec
  /// l'operation.** Elle ne doit jamais etre regeneree au moment de l'envoi :
  /// apres un redemarrage de l'app, le rejeu doit presenter exactement la meme
  /// cle, faute de quoi le serveur creerait un doublon (ARCHITECTURE.md 8).
  factory PendingOperation.create({
    required SyncEntityType entityType,
    required String entityId,
    required SyncOperationKind kind,
    required String method,
    required String path,
    required Map<String, Object?> payload,
    DateTime? createdAt,
    String? id,
    String? idempotencyKey,
  }) {
    return PendingOperation(
      id: id ?? _uuid.v4(),
      entityType: entityType,
      entityId: entityId,
      kind: kind,
      method: method,
      path: path,
      payload: payload,
      idempotencyKey: idempotencyKey ?? _uuid.v4(),
      createdAt: createdAt ?? DateTime.now().toUtc(),
    );
  }

  final String id;
  final SyncEntityType entityType;
  final String entityId;
  final SyncOperationKind kind;
  final String method;
  final String path;
  final Map<String, Object?> payload;
  final String idempotencyKey;
  final int sequence;
  final int attempts;
  final DateTime createdAt;
  final DateTime? nextAttemptAt;
  final String? lastErrorCode;
  final String? lastErrorMessage;
  final bool isDead;

  /// Nombre de tentatives au-dela duquel l'operation est declaree morte.
  /// Volontairement genereux : une operation perdue, c'est une seance perdue.
  static const int maxAttempts = 12;

  bool get hasExhaustedAttempts => attempts >= maxAttempts;

  bool isDue(DateTime now) {
    if (isDead) {
      return false;
    }
    final DateTime? next = nextAttemptAt;
    return next == null || !next.isAfter(now);
  }

  String get payloadJson => jsonEncode(payload);

  PendingOperation copyWith({
    int? sequence,
    int? attempts,
    DateTime? nextAttemptAt,
    bool clearNextAttempt = false,
    String? lastErrorCode,
    String? lastErrorMessage,
    bool? isDead,
    Map<String, Object?>? payload,
  }) {
    return PendingOperation(
      id: id,
      entityType: entityType,
      entityId: entityId,
      kind: kind,
      method: method,
      path: path,
      payload: payload ?? this.payload,
      idempotencyKey: idempotencyKey,
      createdAt: createdAt,
      sequence: sequence ?? this.sequence,
      attempts: attempts ?? this.attempts,
      nextAttemptAt:
          clearNextAttempt ? null : (nextAttemptAt ?? this.nextAttemptAt),
      lastErrorCode: lastErrorCode ?? this.lastErrorCode,
      lastErrorMessage: lastErrorMessage ?? this.lastErrorMessage,
      isDead: isDead ?? this.isDead,
    );
  }

  static Map<String, Object?> decodePayload(String json) {
    final Object? decoded = jsonDecode(json);
    return decoded is Map
        ? Map<String, Object?>.from(decoded)
        : <String, Object?>{};
  }

  @override
  String toString() =>
      'PendingOperation(${entityType.wireValue}/$entityId, ${kind.name}, '
      'attempts: $attempts, dead: $isDead)';
}
