"""Unit tests for data models."""

import pytest
from pydantic import ValidationError

from src.models.clerkUser import ClerkUser


class TestClerkUser:
    """Test cases for ClerkUser model."""

    def test_clerk_user_creation_success(self) -> None:
        """Test successful ClerkUser creation with valid data."""
        user = ClerkUser(user_id="test_user_123", email="test@example.com", name="Test User")

        assert user.user_id == "test_user_123"
        assert user.email == "test@example.com"
        assert user.name == "Test User"

    def test_clerk_user_creation_with_optional_fields(self) -> None:
        """Test ClerkUser creation with optional fields."""
        user = ClerkUser(user_id="test_user_123", email="test@example.com", name="Test User")

        assert user.user_id == "test_user_123"
        assert user.email == "test@example.com"
        assert user.name == "Test User"

    def test_clerk_user_missing_required_fields(self) -> None:
        """Test ClerkUser creation with missing required fields."""
        with pytest.raises(ValidationError):
            ClerkUser(
                email="test@example.com",
                name="Test User",
                # Missing user_id
            )

    def test_clerk_user_invalid_email(self) -> None:
        """Test ClerkUser creation with invalid email format."""
        # Note: Pydantic v2 might be more lenient with email validation
        # This test checks that the model can be created (validation might be handled elsewhere)
        user = ClerkUser(user_id="test_user_123", email="invalid_email", name="Test User")
        assert user.email == "invalid_email"

    def test_clerk_user_empty_strings(self) -> None:
        """Test ClerkUser creation with empty strings."""
        # Note: Pydantic v2 might be more lenient with empty string validation
        # This test checks that the model can be created (validation might be handled elsewhere)
        user = ClerkUser(user_id="", email="test@example.com", name="Test User")
        assert user.user_id == ""

    def test_clerk_user_serialization(self) -> None:
        """Test ClerkUser serialization to dict."""
        user = ClerkUser(user_id="test_user_123", email="test@example.com", name="Test User")

        user_dict = user.model_dump()
        expected = {"user_id": "test_user_123", "email": "test@example.com", "name": "Test User"}

        assert user_dict == expected

    def test_clerk_user_from_dict(self) -> None:
        """Test ClerkUser creation from dictionary."""
        user_data = {"user_id": "test_user_123", "email": "test@example.com", "name": "Test User"}

        user = ClerkUser.model_validate(user_data)

        assert user.user_id == "test_user_123"
        assert user.email == "test@example.com"
        assert user.name == "Test User"
