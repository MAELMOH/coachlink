import 'dart:math';

/// Backoff exponentiel plafonne, avec gigue.
///
/// Utilise par la file de synchronisation et par le client WebSocket.
///
/// La gigue n'est pas cosmetique : sans elle, tous les appareils qui ont perdu
/// le reseau en meme temps (coupure wifi d'une salle de sport) se reconnectent
/// a la même seconde et matraquent l'API.
class ExponentialBackoff {
  ExponentialBackoff({
    this.initial = const Duration(seconds: 1),
    this.maxDelay = const Duration(minutes: 5),
    this.multiplier = 2.0,
    this.jitterRatio = 0.25,
    Random? random,
  })  : assert(multiplier > 1, 'Le multiplicateur doit etre > 1'),
        assert(
          jitterRatio >= 0 && jitterRatio < 1,
          'La gigue doit rester dans [0, 1[',
        ),
        _random = random ?? Random();

  final Duration initial;
  final Duration maxDelay;
  final double multiplier;
  final double jitterRatio;
  final Random _random;

  /// Delai avant la tentative numero [attempt] (1 = premiere reprise).
  Duration delayFor(int attempt) {
    if (attempt <= 0) {
      return Duration.zero;
    }
    final double raw =
        initial.inMilliseconds * pow(multiplier, attempt - 1).toDouble();
    final double capped = min(raw, maxDelay.inMilliseconds.toDouble());

    if (jitterRatio == 0) {
      return Duration(milliseconds: capped.round());
    }
    // Gigue symetrique autour de la valeur cible.
    final double spread = capped * jitterRatio;
    final double jittered = capped - spread + _random.nextDouble() * 2 * spread;
    return Duration(milliseconds: max(0, jittered.round()));
  }

  /// Instant de la prochaine tentative.
  DateTime nextAttemptAt(int attempt, {DateTime? from}) =>
      (from ?? DateTime.now().toUtc()).add(delayFor(attempt));
}
