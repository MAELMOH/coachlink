"""SQLAlchemy models.

Importing this package registers every table on ``Base.metadata`` — which is what
Alembic autogenerate and the test suite need. It must stay free of side effects:
no connection, no mandatory configuration read.
"""

from app.models.base import Base
from app.models.communication import Conversation, DeviceToken, Message, Notification
from app.models.compliance import (
    ActiveClientSnapshot,
    AuditLog,
    BillingEvent,
    Consent,
    DataRequest,
    IdempotencyRecord,
    Subscription,
)
from app.models.identity import (
    ClientProfile,
    CoachClientLink,
    CoachProfile,
    EncryptionKey,
    Invitation,
    RefreshToken,
    User,
)
from app.models.tracking import (
    BodyMeasurement,
    Meal,
    NutritionLog,
    NutritionPlan,
    ProgressPhoto,
)
from app.models.training import (
    Exercise,
    PersonalRecord,
    Program,
    ProgramSession,
    SessionExercise,
    SetLog,
    WorkoutLog,
)

__all__ = [
    "ActiveClientSnapshot",
    "AuditLog",
    "Base",
    "BillingEvent",
    "BodyMeasurement",
    "ClientProfile",
    "CoachClientLink",
    "CoachProfile",
    "Consent",
    "Conversation",
    "DataRequest",
    "DeviceToken",
    "EncryptionKey",
    "Exercise",
    "IdempotencyRecord",
    "Invitation",
    "Meal",
    "Message",
    "Notification",
    "NutritionLog",
    "NutritionPlan",
    "PersonalRecord",
    "Program",
    "ProgramSession",
    "ProgressPhoto",
    "RefreshToken",
    "SessionExercise",
    "SetLog",
    "Subscription",
    "User",
    "WorkoutLog",
]
