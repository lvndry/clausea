"""User repository for data access operations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from motor.core import AgnosticDatabase

from src.core.logging import get_logger
from src.models.user import User
from src.repositories.base_repository import BaseRepository

logger = get_logger(__name__)


class UserRepository(BaseRepository):
    """Repository for user-related database operations."""

    async def upsert(self, db: AgnosticDatabase, user: User) -> User:
        """Create or update a user in the database.

        Args:
            db: Database instance
            user: User object to upsert

        Returns:
            The upserted user
        """
        try:
            existing = await db.users.find_one({"id": user.id})
            now = datetime.now()
            doc = user.model_dump(mode="json")
            doc["updated_at"] = now

            if existing:
                await db.users.update_one({"id": user.id}, {"$set": doc})
                logger.info(f"Updated user {user.id}")
            else:
                doc["created_at"] = now
                await db.users.insert_one(doc)
                logger.info(f"Created user {user.id}")

            return user
        except Exception as e:
            logger.error(f"Error upserting user {user.id}: {e}")
            raise e

    async def find_by_id(self, db: AgnosticDatabase, user_id: str) -> User | None:
        """Get a user by their ID.

        Args:
            db: Database instance
            user_id: User ID

        Returns:
            User or None if not found
        """
        try:
            doc = await db.users.find_one({"id": user_id})
            return User(**doc) if doc else None
        except Exception as e:
            logger.error(f"Error getting user {user_id}: {e}")
            return None

    async def find_by_email(self, db: AgnosticDatabase, email: str) -> User | None:
        """Get a user by their email.

        Args:
            db: Database instance
            email: User email

        Returns:
            User or None if not found
        """
        try:
            doc = await db.users.find_one({"email": email})
            return User(**doc) if doc else None
        except Exception as e:
            logger.error(f"Error getting user by email {email}: {e}")
            return None

    async def find_by_subscription_id(
        self, db: AgnosticDatabase, subscription_id: str
    ) -> User | None:
        """Get a user by their Paddle subscription ID.

        Args:
            db: Database instance
            subscription_id: Paddle subscription ID

        Returns:
            User or None if not found
        """
        try:
            doc = await db.users.find_one({"paddle_subscription_id": subscription_id})
            return User(**doc) if doc else None
        except Exception as e:
            logger.error(f"Error getting user by subscription {subscription_id}: {e}")
            return None

    async def delete(self, db: AgnosticDatabase, user_id: str) -> bool:
        """Delete a user from the database.

        Args:
            db: Database instance
            user_id: User ID

        Returns:
            True if deleted, False otherwise
        """
        try:
            result = await db.users.delete_one({"id": user_id})
            success = result.deleted_count > 0
            if success:
                logger.info(f"Deleted user {user_id}")
            else:
                logger.warning(f"No user found with id {user_id} to delete")
            return bool(success)
        except Exception as e:
            logger.error(f"Error deleting user {user_id}: {e}")
            raise e

    async def find_all(self, db: AgnosticDatabase) -> list[User]:
        """Get all users from the database.

        Args:
            db: Database instance

        Returns:
            List of all users
        """
        try:
            users: list[dict[str, Any]] = await db.users.find().to_list(length=None)
            return [User(**user) for user in users]
        except Exception as e:
            logger.error(f"Error getting all users: {e}")
            raise e

    async def update_fields(
        self, db: AgnosticDatabase, user_id: str, fields: dict[str, Any]
    ) -> bool:
        """Update specific fields for a user.

        Args:
            db: Database instance
            user_id: User ID
            fields: Dictionary of fields to update

        Returns:
            True if updated, False otherwise
        """
        try:
            now = datetime.now()
            fields["updated_at"] = now

            result = await db.users.update_one({"id": user_id}, {"$set": fields}, upsert=False)
            success = result.modified_count > 0
            if success:
                logger.info(f"Updated fields for user {user_id}")
            else:
                logger.warning(f"No user found with id {user_id} to update")
            return bool(success)
        except Exception as e:
            logger.error(f"Error updating fields for user {user_id}: {e}")
            raise e
