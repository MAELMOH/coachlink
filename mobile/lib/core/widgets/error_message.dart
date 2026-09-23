import 'package:flutter/material.dart';

import '../../l10n/generated/app_localizations.dart';
import '../error/api_error.dart';
import '../testing/widget_keys.dart';

/// Traduit une [ApiError] en message affichable.
///
/// Regle : on ne montre **jamais** le `message` brut du serveur a
/// l'utilisateur. Il est en anglais, technique, et peut contenir des details
/// qu'on ne souhaite pas exposer. Il reste utile en log et en test.
String localizeApiError(AppL10n l10n, ApiError error) {
  if (error.isPinningFailure) {
    return l10n.errorCertificatePinning;
  }
  if (error.isNetworkFailure) {
    return l10n.errorNetwork;
  }
  if (error.isTimeout) {
    return l10n.errorTimeout;
  }

  switch (error.code) {
    case ApiErrorCode.consentRequired:
      return l10n.consentBlockedBody;
    case ApiErrorCode.invalidCredentials:
    case ApiErrorCode.tokenExpired:
    case ApiErrorCode.tokenRevoked:
    case ApiErrorCode.unauthorized:
      return l10n.errorUnauthorized;
    case ApiErrorCode.forbidden:
    case ApiErrorCode.linkNotActive:
      return l10n.errorForbidden;
    case ApiErrorCode.notFound:
      return l10n.errorNotFound;
    case ApiErrorCode.validationError:
      return l10n.errorValidation;
    case ApiErrorCode.rateLimited:
      return l10n.errorRateLimited;
    case ApiErrorCode.serverError:
      return l10n.errorServer;
    case ApiErrorCode.subscriptionRequired:
    case ApiErrorCode.readOnlyMode:
      return l10n.trialExpiredBody;
    case ApiErrorCode.invitationExpired:
    case ApiErrorCode.invitationAlreadyUsed:
    case ApiErrorCode.conflict:
    case ApiErrorCode.unknown:
      return l10n.errorUnknown;
  }
}

/// Bloc d'erreur avec action de reprise.
class ErrorMessage extends StatelessWidget {
  const ErrorMessage({required this.error, this.onRetry, super.key});

  final ApiError error;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final AppL10n l10n = AppL10n.of(context);
    final ColorScheme scheme = Theme.of(context).colorScheme;

    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(Icons.error_outline, color: scheme.error, size: 32),
          const SizedBox(height: 12),
          Text(
            localizeApiError(l10n, error),
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodyMedium,
          ),
          if (onRetry != null) ...<Widget>[
            const SizedBox(height: 16),
            OutlinedButton(
              key: K.errorRetryButton,
              onPressed: onRetry,
              child: Text(l10n.commonRetry),
            ),
          ],
        ],
      ),
    );
  }
}
