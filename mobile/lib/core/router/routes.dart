/// Chemins de navigation, centralises pour eviter les chaines en dur.
abstract final class Routes {
  static const String splash = '/';
  static const String signIn = '/sign-in';
  static const String signUp = '/sign-up';

  /// Ecran de consentement RGPD **bloquant**.
  static const String consent = '/consent';

  static const String myData = '/my-data';
  static const String trialExpired = '/trial-expired';

  // Coach
  static const String coachHome = '/coach';
  static const String coachInvite = '/coach/invite';
  static const String coachClients = '/coach/clients';
  static const String exerciseLibrary = '/coach/exercises';

  // Client
  static const String clientHome = '/client';
  static const String clientWeek = '/client/week';
  static const String clientProgress = '/client/progress';

  /// Deep link d'invitation : `https://<host>/invite/<code>` et
  /// `coachlink://invite/<code>`.
  static const String invite = '/invite';
  static String inviteWithCode(String code) => '/invite/$code';

  /// Chemins accessibles sans etre authentifie.
  static const Set<String> publicPaths = <String>{
    splash,
    signIn,
    signUp,
    invite,
  };

  static bool isPublic(String location) {
    if (publicPaths.contains(location)) {
      return true;
    }
    return location.startsWith('$invite/');
  }
}
