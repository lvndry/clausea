from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from motor.core import AgnosticDatabase
from pydantic import BaseModel

from src.core.database import get_db
from src.core.logging import get_logger
from src.models.conversation import Conversation, Message
from src.services.service_factory import create_conversation_service

logger = get_logger(__name__)

router = APIRouter(prefix="/conversations")


class CreateConversationRequest(BaseModel):
    user_id: str
    product_name: str
    product_slug: str
    company_name: str | None = None
    product_description: str | None = None
    title: str | None = None


class SendMessageRequest(BaseModel):
    conversation_id: str
    message: str


class PatchConversationRequest(BaseModel):
    title: str | None = None
    archived: bool | None = None
    pinned: bool | None = None
    tags: list[str] | None = None
    product_name: str | None = None
    company_name: str | None = None
    product_description: str | None = None


@router.post("")
async def create_new_conversation(
    request: CreateConversationRequest, db: AgnosticDatabase = Depends(get_db)
) -> Conversation:
    """Create a new conversation."""
    try:
        service = create_conversation_service()
        created_conversation = await service.create_conversation(
            db,
            user_id=request.user_id,
            product_name=request.product_name,
            product_slug=request.product_slug,
            company_name=request.company_name,
            product_description=request.product_description,
            title=request.title,
        )
        return created_conversation
    except Exception as e:
        logger.error(f"Error creating conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str, db: AgnosticDatabase = Depends(get_db)
) -> Conversation:
    """Get a conversation by ID."""
    try:
        service = create_conversation_service()
        conversation = await service.get_conversation_by_id(db, conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conversation
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/user/{user_id}")
async def get_user_conversations_route(
    user_id: str,
    product_slug: str | None = None,
    archived: bool | None = None,
    pinned: bool | None = None,
    db: AgnosticDatabase = Depends(get_db),
) -> list[Conversation]:
    """Get all conversations for a user."""
    try:
        query: dict[str, Any] = {"user_id": user_id}
        if product_slug is not None:
            query["product_slug"] = product_slug
        if archived is not None:
            query["archived"] = archived
        if pinned is not None:
            query["pinned"] = pinned

        conversations: list[Conversation] = (
            await db.conversations.find(query).sort("last_message_at", -1).to_list(length=None)
        )
        return conversations
    except Exception as e:
        logger.error(f"Error getting user conversations: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{conversation_id}/messages")
async def send_message(
    request: SendMessageRequest, db: AgnosticDatabase = Depends(get_db)
) -> dict[str, Message]:
    """Send a message in a conversation."""
    try:
        try:
            service = create_conversation_service()
            result: dict[str, Message] = await service.send_message(
                db, request.conversation_id, request.message
            )
            return result
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{conversation_id}/messages/stream")
async def send_message_stream(
    conversation_id: str, request: SendMessageRequest, db: AgnosticDatabase = Depends(get_db)
) -> StreamingResponse:
    """Send a message and stream the response."""
    try:
        service = create_conversation_service()
        return StreamingResponse(
            service.stream_message(db, conversation_id, request.message),
            media_type="text/event-stream",
        )
    except Exception as e:
        logger.error(f"Error streaming message: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.patch("/{conversation_id}")
async def patch_conversation(
    conversation_id: str,
    request: PatchConversationRequest,
    db: AgnosticDatabase = Depends(get_db),
) -> dict[str, bool]:
    """Patch conversation metadata fields."""
    try:
        service = create_conversation_service()
        success = await service.patch_conversation(
            db, conversation_id, request.model_dump(exclude_none=True)
        )
        if not success:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error patching conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{conversation_id}/upload")
async def upload_document(
    conversation_id: str,
    file: UploadFile = File(...),
    product_name: str = Form(...),
    company_name: str = Form(None),
    product_description: str = Form(None),
    db: AgnosticDatabase = Depends(get_db),
) -> dict[str, Any]:
    """Upload a document to a conversation."""
    try:
        # Read the uploaded file
        content = await file.read()
        try:
            service = create_conversation_service()
            result = await service.upload_document(
                db=db,
                conversation_id=conversation_id,
                file_content=content,
                filename=file.filename or "",
                content_type=file.content_type or "application/octet-stream",
                product_name=product_name,
                company_name=company_name,
                product_description=product_description,
            )
            if not result.success:
                if not result.is_legal_document:
                    raise HTTPException(
                        status_code=400,
                        detail="Document is not classified as a legal document. Please upload a legal document such as a privacy policy, terms of service, or similar legal document.",
                    )
                else:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Document processing failed: {result.error_message}",
                    )
            if not result.document:
                raise HTTPException(
                    status_code=500,
                    detail=f"Document processing failed: {result.error_message}",
                )

            return {
                "message": "Document uploaded and processed successfully",
                "document_id": result.document.id,
                "classification": result.document.doc_type,
                "analysis_available": result.analysis is not None,
            }
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading document: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str, db: AgnosticDatabase = Depends(get_db)
) -> dict[str, bool]:
    """Delete a conversation."""
    try:
        service = create_conversation_service()
        success = await service.delete_conversation(db, conversation_id)
        if not success:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
