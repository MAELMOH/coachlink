import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_timezone/flutter_timezone.dart';

/// Fournit le fuseau IANA du device, ex. `Europe/Paris`.
///
/// « La seance du jour » se resout dans le fuseau de l'utilisateur, pas en UTC :
/// sinon un client qui ouvre l'app a 23h voit la seance du lendemain
/// (arbitrage Tech Lead, 2026-09-22). Le fuseau est envoye a la connexion et
/// remis a jour s'il change.
abstract class DeviceTimezone {
  Future<String> current();
}

class PlatformDeviceTimezone implements DeviceTimezone {
  const PlatformDeviceTimezone();

  static const String fallback = 'Europe/Paris';

  @override
  Future<String> current() async {
    try {
      final String name = await FlutterTimezone.getLocalTimezone();
      return name.isEmpty ? fallback : name;
    } on Object {
      // Plateforme sans plugin (tests headless, desktop) : on ne bloque pas
      // une connexion pour un fuseau, le serveur corrigera au prochain appel.
      return fallback;
    }
  }
}

class FixedDeviceTimezone implements DeviceTimezone {
  const FixedDeviceTimezone(this.value);

  final String value;

  @override
  Future<String> current() async => value;
}

final Provider<DeviceTimezone> deviceTimezoneProvider =
    Provider<DeviceTimezone>(
  (Ref ref) => const PlatformDeviceTimezone(),
);
