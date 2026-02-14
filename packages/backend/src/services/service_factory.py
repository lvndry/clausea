"""Service factory for creating service instances with proper dependencies.

This module provides helper functions to create service instances with
the correct repository dependencies, reducing boilerplate in routes and
components.
"""

from __future__ import annotations

from src.repositories.conversation_repository import ConversationRepository
from src.repositories.document_repository import DocumentRepository
from src.repositories.product_repository import ProductRepository
from src.repositories.user_repository import UserRepository
from src.services.conversation_service import ConversationService
from src.services.document_service import DocumentService
from src.services.product_service import ProductService
from src.services.user_service import UserService


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
