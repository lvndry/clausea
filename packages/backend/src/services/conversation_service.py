"""Conversation service for business logic operations."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from motor.core import AgnosticDatabase

from src.core.logging import get_logger
from src.document_processor import DocumentProcessingResult, DocumentProcessor
from src.llm import acompletion_with_fallback
from src.models.conversation import Conversation, Message
from src.rag import get_answer, get_answer_stream
from src.repositories.conversation_repository import ConversationRepository
from src.services.embedding_service import EmbeddingService

logger = get_logger(__name__)


class ConversationService:
    """Service for conversation-related business logic."""

    def __init__(self, conversation_repo: ConversationRepository) -> None:
        """Initialize ConversationService with repository dependency."""
        self._conversation_repo = conversation_repo

    async def create_conversation(
        self,
        db: AgnosticDatabase,
        user_id: str,
        product_name: str,
        product_slug: str,
        company_name: str | None = None,
        product_description: str | None = None,
        title: str | None = None,
    ) -> Conversation:
        """Create a new conversation."""
        conversation = Conversation(
            user_id=user_id,
            product_name=product_name,
            product_slug=product_slug,
            company_name=company_name,
            product_description=product_description,
            title=title,
        )
        return await self._conversation_repo.create(db, conversation)

    async def get_conversation_by_id(
        self, db: AgnosticDatabase, conversation_id: str
    ) -> Conversation | None:
        """Get a conversation by its ID."""
        return await self._conversation_repo.find_by_id(db, conversation_id)

    async def get_user_conversations(
        self, db: AgnosticDatabase, user_id: str
    ) -> list[Conversation]:
        """Get all conversations for a user."""
        conversations: list[Conversation] = await self._conversation_repo.find_by_user_id(
            db, user_id
        )
        return conversations

    async def get_all_conversations(self, db: AgnosticDatabase) -> list[Conversation]:
        """Get all conversations from the database."""
        conversations: list[Conversation] = await self._conversation_repo.find_all(db)
        return conversations

    async def update_conversation(self, db: AgnosticDatabase, conversation: Conversation) -> bool:
        """Update a conversation in the database."""
        updated: bool = await self._conversation_repo.update(db, conversation)
        return updated

    async def patch_conversation(
        self, db: AgnosticDatabase, conversation_id: str, data: dict[str, Any]
    ) -> bool:
        """Patch conversation fields in the database."""
        # Business logic: validate allowed fields
        allowed_fields = {
            "title",
            "mode",
            "archived",
            "pinned",
            "tags",
            "product_name",
            "company_name",
            "product_description",
        }
        update_data = {k: v for k, v in data.items() if k in allowed_fields}
        if not update_data:
            return True

        updated: bool = await self._conversation_repo.patch(db, conversation_id, update_data)
        return updated

    async def delete_conversation(self, db: AgnosticDatabase, conversation_id: str) -> bool:
        """Delete a conversation from the database."""
        deleted: bool = await self._conversation_repo.delete(db, conversation_id)
        return deleted

    async def add_message_to_conversation(
        self, db: AgnosticDatabase, conversation_id: str, message: Message
    ) -> bool:
        """Add a message to a conversation."""
        added: bool = await self._conversation_repo.add_message(db, conversation_id, message)
        return added

    async def add_document_to_conversation(
        self, db: AgnosticDatabase, conversation_id: str, document_id: str
    ) -> bool:
        """Add a document to a conversation."""
        added: bool = await self._conversation_repo.add_document(db, conversation_id, document_id)
        return added

    async def get_conversation_messages(
        self, db: AgnosticDatabase, conversation_id: str
    ) -> list[Message]:
        """Get all messages for a conversation."""
        conversation = await self.get_conversation_by_id(db, conversation_id)
        return conversation.messages if conversation else []

    async def get_conversation_documents(
        self, db: AgnosticDatabase, conversation_id: str
    ) -> list[str]:
        """Get all document IDs for a conversation."""
        conversation = await self.get_conversation_by_id(db, conversation_id)
        return conversation.documents if conversation else []

    async def send_message(
        self, db: AgnosticDatabase, conversation_id: str, message_text: str
    ) -> dict[str, Message]:
        """Send a message in a conversation and get AI response."""
        conversation = await self.get_conversation_by_id(db, conversation_id)
        if not conversation:
            raise ValueError("Conversation not found")

        was_first_message = conversation.message_count == 0

        user_message = Message(role="user", content=message_text)
        await self.add_message_to_conversation(db, conversation_id, user_message)

        ai_response = await get_answer(message_text, conversation.product_slug)
        ai_message = Message(role="assistant", content=ai_response)
        await self.add_message_to_conversation(db, conversation_id, ai_message)

        # Auto-generate a conversation title after first exchange if needed
        try:
            if was_first_message and (
                not conversation.title or conversation.title.lower() == "new conversation"
            ):
                new_title = await self._generate_conversation_title(
                    product_name=conversation.product_name,
                    company_name=conversation.company_name,
                    user_prompt=message_text,
                    ai_answer=ai_response,
                )
                if new_title:
                    await self.patch_conversation(db, conversation_id, {"title": new_title})
        except Exception as e:
            logger.warning(f"Title generation failed for conversation {conversation_id}: {e}")

        return {"user_message": user_message, "ai_message": ai_message}

    async def stream_message(
        self, db: AgnosticDatabase, conversation_id: str, message_text: str
    ) -> AsyncGenerator[str, None]:
        """Send a message and stream the AI response."""
        conversation = await self.get_conversation_by_id(db, conversation_id)
        if not conversation:
            raise ValueError("Conversation not found")

        was_first_message = conversation.message_count == 0

        # Save user message
        user_message = Message(role="user", content=message_text)
        await self.add_message_to_conversation(db, conversation_id, user_message)

        # Stream AI response
        full_response = []
        async for chunk in get_answer_stream(message_text, conversation.product_slug):
            full_response.append(chunk)
            yield chunk

        ai_response_text = "".join(full_response)
        ai_message = Message(role="assistant", content=ai_response_text)
        await self.add_message_to_conversation(db, conversation_id, ai_message)

        # Auto-generate title
        try:
            if was_first_message and (
                not conversation.title or conversation.title.lower() == "new conversation"
            ):
                new_title = await self._generate_conversation_title(
                    product_name=conversation.product_name,
                    company_name=conversation.company_name,
                    user_prompt=message_text,
                    ai_answer=ai_response_text,
                )
                if new_title:
                    await self.patch_conversation(db, conversation_id, {"title": new_title})
        except Exception as e:
            logger.warning(f"Title generation failed for conversation {conversation_id}: {e}")

    async def _generate_conversation_title(
        self, product_name: str, company_name: str | None, user_prompt: str, ai_answer: str
    ) -> str:
        """Generate a short, descriptive conversation title using a lightweight model."""
        system_prompt = (
            "You create concise, descriptive conversation titles (4-7 words). "
            "Avoid quotes, punctuation at the end, and product names unless essential."
        )
        company_info = f"Company: {company_name}\n" if company_name else ""
        user_content = (
            f"Product: {product_name}\n"
            f"{company_info}"
            f"User question: {user_prompt}\n"
            f"Assistant answer (truncated): {ai_answer[:500]}\n\n"
            "Title:"
        )

        try:
            resp = await acompletion_with_fallback(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.5,
            )
            choice = resp.choices[0]
            if not hasattr(choice, "message"):
                raise ValueError("Unexpected response format: missing message attribute")
            message = choice.message  # type: ignore[attr-defined]
            if not message:
                raise ValueError("Unexpected response format: message is None")
            content = message.content  # type: ignore[attr-defined]
            if not content:
                raise ValueError("Empty response from LLM")
            title = content.strip()
            # Post-process length and cleanliness
            if len(title) > 60:
                title = title[:60].rstrip()
            return title or "New Conversation"
        except Exception as e:
            logger.warning(f"LLM title generation error: {e}")
            # Fallback: derive from user prompt
            fallback = user_prompt.strip().split("\n")[0][:60].rstrip()
            return fallback or "New Conversation"

    async def upload_document(
        self,
        db: AgnosticDatabase,
        conversation_id: str,
        file_content: bytes,
        filename: str,
        content_type: str,
        product_name: str | None = None,
        company_name: str | None = None,
        product_description: str | None = None,
    ) -> DocumentProcessingResult:
        """Upload a document to a conversation."""
        conversation = await self.get_conversation_by_id(db, conversation_id)
        if not conversation:
            raise ValueError("Conversation not found")

        processor = DocumentProcessor()
        result = await processor.process_document(
            file_content=file_content,
            filename=filename,
            content_type=content_type,
            product_id=conversation.product_slug,
        )

        if not result.success:
            return result

        if not result.document:
            return result

        await self.add_document_to_conversation(db, conversation_id, result.document.id)
        try:
            embedding_service = EmbeddingService()
            await embedding_service.embed_document(
                result.document, namespace=conversation.product_slug
            )
        except Exception as e:
            logger.warning(f"Embedding uploaded document failed: {e}")

        if product_name or company_name or product_description:
            conversation.product_name = product_name or conversation.product_name
            conversation.company_name = company_name or conversation.company_name
            conversation.product_description = (
                product_description or conversation.product_description
            )
            await self.update_conversation(db, conversation)

        return result
