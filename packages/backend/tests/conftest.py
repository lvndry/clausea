"""Pytest configuration and shared fixtures for Clausea tests."""

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.models.clerkUser import ClerkUser

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

pytest_plugins = ["pytest_asyncio"]


@pytest.fixture
def mock_clerk_user() -> ClerkUser:
    """Mock ClerkUser for testing."""

    return ClerkUser(user_id="test_user_123", email="test@example.com", name="Test User")


@pytest.fixture
def mock_jwt_payload() -> dict[str, Any]:
    """Mock JWT payload for testing."""
    return {
        "sub": "test_user_123",
        "email": "test@example.com",
        "name": "Test User",
        "iss": "https://clerk.example.com",
    }


@pytest.fixture
def mock_http_client() -> AsyncMock:
    """Mock HTTP client for external API calls."""
    return AsyncMock()


@pytest.fixture
def mock_llm_service() -> AsyncMock:
    """Mock LLM service for testing."""
    service = AsyncMock()
    service.analyze_document.return_value = {
        "risk_score": 5.0,
        "confidence": 0.85,
        "summary": "Test analysis summary",
    }
    return service
