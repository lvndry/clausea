"""Service factory for creating service instances with proper dependencies.

This module provides helper functions to create service instances with
the correct repository dependencies, reducing boilerplate in routes and
components.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.repositories.conversation_repository import ConversationRepository
from src.repositories.document_repository import DocumentRepository
from src.repositories.indexation_subscription_repository import (
    IndexationSubscriptionRepository,
)
from src.repositories.product_repository import ProductRepository
from src.repositories.user_repository import UserRepository
from src.services.conversation_service import ConversationService
from src.services.document_service import DocumentService
from src.services.indexation_notification_service import IndexationNotificationService
from src.services.product_service import ProductService
from src.services.user_service import UserService

if TYPE_CHECKING:
    from src.services.pipeline_service import PipelineService


def create_product_service() -> ProductService:
    """Create a ProductService with repository dependencies.

    Returns:
        Configured ProductService instance
    """
    product_repo = ProductRepository()
    document_repo = DocumentRepository()
    return ProductService(product_repo, document_repo)


def create_document_service() -> DocumentService:
    """Create a DocumentService with repository dependencies.

    Returns:
        Configured DocumentService instance
    """
    document_repo = DocumentRepository()
    product_repo = ProductRepository()
    return DocumentService(document_repo, product_repo)


def create_services() -> tuple[ProductService, DocumentService]:
    """Create both ProductService and DocumentService with shared repositories.

    This is more efficient than creating them separately because they share
    the same repository instances.

    Returns:
        Tuple of (ProductService, DocumentService)
    """
    product_repo = ProductRepository()
    document_repo = DocumentRepository()

    product_service = ProductService(product_repo, document_repo)
    document_service = DocumentService(document_repo, product_repo)

    return product_service, document_service


def create_pipeline_service() -> PipelineService:
    """Create a PipelineService with repository dependencies.

    Returns:
        Configured PipelineService instance
    """
    # Lazy imports to avoid circular dependency:
    # service_factory -> pipeline_service -> pipeline -> service_factory
    from src.repositories.pipeline_repository import PipelineRepository as _PipelineRepo
    from src.services.pipeline_service import PipelineService as _PipelineSvc

    pipeline_repo = _PipelineRepo()
    return _PipelineSvc(pipeline_repo)


def create_indexation_notification_service() -> IndexationNotificationService:
    repo = IndexationSubscriptionRepository()
    return IndexationNotificationService(repo)


def create_user_service() -> UserService:
    """Create a UserService with repository dependencies.

    Returns:
        Configured UserService instance
    """
    user_repo = UserRepository()
    return UserService(user_repo)


def create_conversation_service() -> ConversationService:
    """Create a ConversationService with repository dependencies.

    Returns:
        Configured ConversationService instance
    """
    conversation_repo = ConversationRepository()
    return ConversationService(conversation_repo)
