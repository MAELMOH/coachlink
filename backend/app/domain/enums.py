"""Domain enumerations — the vocabulary shared by models, schemas and services.

Mirrors ARCHITECTURE.md §4. Values are the exact strings stored in PostgreSQL and
returned by the API, so renaming one is a breaking API change *and* a migration.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "BillingEventType",
    "BillingProviderName",
    "CoachingMode",
    "ConsentPurpose",
    "DataRequestStatus",
    "DataRequestType",
    "DevicePlatform",
    "MealSlot",
    "MeasurementSource",
    "MediaLicense",
    "NotificationType",
    "PhotoAngle",
    "PlanCode",
    "ProgramStatus",
    "SubjectType",
    "SubscriptionStatus",
    "UserRole",
    "WorkoutStatus",
    "ExerciseSource",
    "LinkStatus",
]


class UserRole(StrEnum):
    COACH = "coach"
    CLIENT = "client"


class CoachingMode(StrEnum):
    """`presentiel` => messaging disabled + simplified tracking (ARCHITECTURE.md §4)."""

    PRESENTIEL = "presentiel"
    DISTANCE = "distance"


class LinkStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    PAUSED = "paused"
    REVOKED = "revoked"


class MediaLicense(StrEnum):
    """Mandatory on every media so the legal audit stays feasible (ARCHITECTURE.md §6)."""

    PUBLIC_DOMAIN = "public_domain"
    COACH_OWNED = "coach_owned"


class ExerciseSource(StrEnum):
    SEED = "seed"
    COACH = "coach"


class ProgramStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class WorkoutStatus(StrEnum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class MeasurementSource(StrEnum):
    CLIENT = "client"
    COACH = "coach"


class PhotoAngle(StrEnum):
    FRONT = "front"
    SIDE = "side"
    BACK = "back"


class MealSlot(StrEnum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


class ConsentPurpose(StrEnum):
    TOS = "tos"
    PRIVACY = "privacy"
    HEALTH_DATA = "health_data"
    PROGRESS_PHOTOS = "progress_photos"
    MARKETING = "marketing"


#: Without these three, every business route answers 403 CONSENT_REQUIRED (§5.2).
REQUIRED_CONSENTS: frozenset[ConsentPurpose] = frozenset(
    {ConsentPurpose.TOS, ConsentPurpose.PRIVACY, ConsentPurpose.HEALTH_DATA}
)

#: Opt-in, unchecked by default. Never pre-granted.
OPTIONAL_CONSENTS: frozenset[ConsentPurpose] = frozenset(
    {ConsentPurpose.PROGRESS_PHOTOS, ConsentPurpose.MARKETING}
)


class DataRequestType(StrEnum):
    EXPORT = "export"
    DELETION = "deletion"


class DataRequestStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NotificationType(StrEnum):
    SESSION_REMINDER = "session_reminder"
    PROGRAM_PUBLISHED = "program_published"
    MESSAGE_RECEIVED = "message_received"
    TRIAL_ENDING = "trial_ending"
    EXPORT_READY = "export_ready"


class DevicePlatform(StrEnum):
    IOS = "ios"
    ANDROID = "android"


class SubjectType(StrEnum):
    CLIENT = "client"
    COACH = "coach"


class SubscriptionStatus(StrEnum):
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"


class PlanCode(StrEnum):
    CLIENT_MONTHLY = "client_monthly"
    COACH_COMMISSION = "coach_commission"


class BillingProviderName(StrEnum):
    MANUAL = "manual"
    STRIPE = "stripe"


class BillingEventType(StrEnum):
    TRIAL_STARTED = "trial_started"
    TRIAL_ENDED = "trial_ended"
    SUBSCRIPTION_STARTED = "subscription_started"
    SUBSCRIPTION_CANCELED = "subscription_canceled"
    USAGE_REPORTED = "usage_reported"
    PAYMENT_SUCCEEDED = "payment_succeeded"
    PAYMENT_FAILED = "payment_failed"
