import 'dart:convert';

import 'package:flutter/foundation.dart';

/// Evenements temps reel diffuses par le serveur (ARCHITECTURE.md 8).
enum RealtimeEventType {
  programPublished('program.published'),
  workoutCompleted('workout.completed'),
  messageCreated('message.created'),
  measurementCreated('measurement.created'),
  unknown('unknown');

  const RealtimeEventType(this.wireValue);

  final String wireValue;

  static RealtimeEventType fromWire(String? value) {
    for (final RealtimeEventType type in RealtimeEventType.values) {
      if (type.wireValue == value) {
        return type;
      }
    }
    return RealtimeEventType.unknown;
  }
}

@immutable
class RealtimeEvent {
  const RealtimeEvent({
    required this.type,
    required this.channel,
    required this.payload,
    this.rawType,
  });

  final RealtimeEventType type;

  /// `user:{id}` ou `link:{id}`.
  final String channel;
  final Map<String, Object?> payload;
  final String? rawType;

  static RealtimeEvent? tryParse(Object? frame) {
    final Object? decoded = frame is String ? _decode(frame) : frame;
    if (decoded is! Map) {
      return null;
    }
    final Object? rawPayload = decoded['payload'] ?? decoded['data'];
    return RealtimeEvent(
      type: RealtimeEventType.fromWire(decoded['type'] as String?),
      channel: (decoded['channel'] as String?) ?? '',
      payload: rawPayload is Map
          ? Map<String, Object?>.from(rawPayload)
          : const <String, Object?>{},
      rawType: decoded['type'] as String?,
    );
  }

  static Object? _decode(String frame) {
    try {
      return jsonDecode(frame);
    } on FormatException {
      return null;
    }
  }

  @override
  String toString() => 'RealtimeEvent(${rawType ?? type.wireValue}, $channel)';
}
