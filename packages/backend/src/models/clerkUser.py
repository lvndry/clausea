from pydantic import BaseModel, Field


class ClerkUser(BaseModel):
    """Represents an authenticated user from Clerk"""

    user_id: str = Field(..., description="Unique user identifier from Clerk")
    email: str = Field(..., description="User's email address")
    name: str | None = Field(None, description="User's display name")
