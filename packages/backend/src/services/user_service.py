"""User service for business logic operations."""

from __future__ import annotations

from typing import Any

from motor.core import AgnosticDatabase

from src.core.logging import get_logger
from src.models.user import User
from src.repositories.user_repository import UserRepository

logger = get_logger(__name__)


class UserService:
    """Service for user-related business logic."""

    def __init__(self, user_repo: UserRepository) -> None:
        """Initialize UserService with repository dependency."""
        self._user_repo = user_repo

    async def upsert_user(self, db: AgnosticDatabase, user: User) -> User:
        """Create or update a user in the database.

        Args:
            db: Database instance
            user: User object

        Returns:
            The upserted user
        """
        return await self._user_repo.upsert(db, user)

    async def get_user_by_id(self, db: AgnosticDatabase, user_id: str) -> User | None:
        """Get a user by their ID.

        Args:
            db: Database instance
            user_id: User ID

        Returns:
            User or None if not found
        """
        return await self._user_repo.find_by_id(db, user_id)

    async def get_user_by_email(self, db: AgnosticDatabase, email: str) -> User | None:
        """Get a user by their email.

        Args:
            db: Database instance
            email: User email

        Returns:
            User or None if not found
        """
        return await self._user_repo.find_by_email(db, email)

    async def get_user_by_subscription_id(
        self, db: AgnosticDatabase, subscription_id: str
    ) -> User | None:
        """Get a user by their Paddle subscription ID.

        Args:
            db: Database instance
            subscription_id: Paddle subscription ID

        Returns:
            User or None if not found
        """
        return await self._user_repo.find_by_subscription_id(db, subscription_id)

    async def delete_user(self, db: AgnosticDatabase, user_id: str) -> bool:
        """Delete a user from the database.

        Args:
            db: Database instance
            user_id: User ID

        Returns:
            True if deleted
        """
        deleted: bool = await self._user_repo.delete(db, user_id)
        return deleted

    async def set_user_onboarding_completed(self, db: AgnosticDatabase, user_id: str) -> bool:
        """Mark a user's onboarding as completed.

        Args:
            db: Database instance
            user_id: User ID

        Returns:
            True if updated
        """
        onboarding_completed: bool = await self._user_repo.update_fields(
            db, user_id, {"onboarding_completed": True}
        )
        return onboarding_completed

    async def get_all_users(self, db: AgnosticDatabase) -> list[User]:
        """Get all users from the database.

        Args:
            db: Database instance

        Returns:
            List of all users
        """
        all_user: list[User] = await self._user_repo.find_all(db)
        return all_user

    async def update_user_profile(
        self, db: AgnosticDatabase, user_id: str, profile_data: dict[str, Any]
    ) -> bool:
        """Update a user's profile information.

        Args:
            db: Database instance
            user_id: User ID
            profile_data: Dictionary of profile fields to update

        Returns:
            True if updated
        """
        updated: bool = await self._user_repo.update_fields(db, user_id, profile_data)
        return updated
