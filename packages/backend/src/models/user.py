from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class UserTier(str, Enum):
    FREE = "free"
    INDIVIDUAL = "individual"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"


class User(BaseModel):
    id: str
    email: str
    first_name: str | None = None
    last_name: str | None = None
    tier: UserTier = UserTier.FREE
    onboarding_completed: bool = False

    monthly_usage: dict[str, int] = Field(default_factory=dict)

    paddle_customer_id: str | None = None
    paddle_subscription_id: str | None = None
    subscription_status: str | None = None
    subscription_started_at: datetime | None = None
    subscription_canceled_at: datetime | None = None
    subscription_current_period_end: datetime | None = None

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
