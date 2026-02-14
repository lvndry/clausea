"""Conversation repository for data access operations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from motor.core import AgnosticDatabase

from src.core.logging import get_logger
from src.models.conversation import Conversation, Message
from src.repositories.base_repository import BaseRepository

logger = get_logger(__name__)


class ConversationRepository(BaseRepository):
    """Repository for conversation-related database operations."""

    async def create(self, db: AgnosticDatabase, conversation: Conversation) -> Conversation:
        """Create a new conversation in the database.

        Args:
            db: Database instance
            conversation: Conversation object

        Returns:
            The created conversation
        """
        try:
            doc = conversation.model_dump(mode="json")
            await db.conversations.insert_one(doc)
            logger.info(f"Created conversation {conversation.id}")
            return conversation
        except Exception as e:
            logger.error(f"Error creating conversation: {e}")
            raise e

    async def find_by_id(self, db: AgnosticDatabase, conversation_id: str) -> Conversation | None:
        """Get a conversation by its ID.

        Args:
            db: Database instance
            conversation_id: Conversation ID

        Returns:
            Conversation or None if not found
        """
        try:
            doc = await db.conversations.find_one({"id": conversation_id})
            return Conversation(**doc) if doc else None
        except Exception as e:
            logger.error(f"Error getting conversation {conversation_id}: {e}")
            return None

    async def find_by_user_id(self, db: AgnosticDatabase, user_id: str) -> list[Conversation]:
        """Get all conversations for a user.

        Args:
            db: Database instance
            user_id: User ID

        Returns:
            List of conversations
        """
        try:
            conversations: list[dict[str, Any]] = await db.conversations.find(
                {"user_id": user_id}
            ).to_list(length=None)
            return [Conversation(**conv) for conv in conversations]
        except Exception as e:
            logger.error(f"Error getting conversations for user {user_id}: {e}")
            raise e

    async def find_all(self, db: AgnosticDatabase) -> list[Conversation]:
        """Get all conversations from the database.

        Args:
            db: Database instance

        Returns:
            List of all conversations
        """
        try:
            conversations: list[dict[str, Any]] = await db.conversations.find().to_list(length=None)
            return [Conversation(**conv) for conv in conversations]
        except Exception as e:
            logger.error(f"Error getting all conversations: {e}")
            raise e

    async def update(self, db: AgnosticDatabase, conversation: Conversation) -> bool:
        """Update a conversation in the database.

        Args:
            db: Database instance
            conversation: Conversation object

        Returns:
            True if updated, False otherwise
        """
        try:
            doc = conversation.model_dump(mode="json")
            doc["updated_at"] = datetime.now()

            result = await db.conversations.update_one({"id": conversation.id}, {"$set": doc})
            return bool(result.modified_count > 0)
        except Exception as e:
            logger.error(f"Error updating conversation {conversation.id}: {e}")
            raise e

    async def patch(
        self, db: AgnosticDatabase, conversation_id: str, fields: dict[str, Any]
    ) -> bool:
        """Patch specific fields in a conversation.

        Args:
            db: Database instance
            conversation_id: Conversation ID
            fields: Dictionary of fields to update

        Returns:
            True if updated, False otherwise
        """
        try:
            fields["updated_at"] = datetime.now()

            result = await db.conversations.update_one({"id": conversation_id}, {"$set": fields})
            success = result.modified_count > 0
            if success:
                logger.info(f"Patched conversation {conversation_id}")
            return bool(success)
        except Exception as e:
            logger.error(f"Error patching conversation {conversation_id}: {e}")
            raise e

    async def delete(self, db: AgnosticDatabase, conversation_id: str) -> bool:
        """Delete a conversation from the database.

        Args:
            db: Database instance
            conversation_id: Conversation ID

        Returns:
            True if deleted, False otherwise
        """
        try:
            result = await db.conversations.delete_one({"id": conversation_id})
            success = result.deleted_count > 0
            if success:
                logger.info(f"Deleted conversation {conversation_id}")
            return bool(success)
        except Exception as e:
            logger.error(f"Error deleting conversation {conversation_id}: {e}")
            raise e

    async def add_message(
        self, db: AgnosticDatabase, conversation_id: str, message: Message
    ) -> bool:
        """Add a message to a conversation.

        Args:
            db: Database instance
            conversation_id: Conversation ID
            message: Message object

        Returns:
            True if successful
        """
        try:
            message_doc = message.model_dump(mode="json")
            result = await db.conversations.update_one(
                {"id": conversation_id},
                {"$push": {"messages": message_doc}, "$set": {"updated_at": datetime.now()}},
            )
            success = result.modified_count > 0
            if success:
                logger.info(f"Added message to conversation {conversation_id}")
            return bool(success)
        except Exception as e:
            logger.error(f"Error adding message to conversation {conversation_id}: {e}")
            raise e

    async def add_document(
        self, db: AgnosticDatabase, conversation_id: str, document_id: str
    ) -> bool:
        """Add a document ID to a conversation.

        Args:
            db: Database instance
            conversation_id: Conversation ID
            document_id: Document ID

        Returns:
            True if successful
        """
        try:
            result = await db.conversations.update_one(
                {"id": conversation_id},
                {
                    "$addToSet": {"document_ids": document_id},
                    "$set": {"updated_at": datetime.now()},
                },
            )
            success = result.modified_count > 0
            if success:
                logger.info(f"Added document {document_id} to conversation {conversation_id}")
            return bool(success)
        except Exception as e:
            logger.error(f"Error adding document to conversation {conversation_id}: {e}")
            raise e
