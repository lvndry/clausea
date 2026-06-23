from unittest.mock import patch

from src.models.user import User, UserTier
from src.services.subscription_sync import (
    apply_subscription_data_to_user,
    resolve_tier_from_price_id,
    user_needs_subscription_sync,
)


def test_resolve_tier_from_price_id_pro_monthly() -> None:
    with patch("src.services.subscription_sync.config") as mock_config:
        mock_config.paddle.price_pro_monthly = "pri_monthly"
        mock_config.paddle.price_pro_annual = "pri_annual"
        assert resolve_tier_from_price_id("pri_monthly") == UserTier.PRO


def test_resolve_tier_from_price_id_unknown() -> None:
    with patch("src.services.subscription_sync.config") as mock_config:
        mock_config.paddle.price_pro_monthly = "pri_monthly"
        mock_config.paddle.price_pro_annual = "pri_annual"
        assert resolve_tier_from_price_id("pri_other") == UserTier.FREE


def test_apply_subscription_data_to_user_sets_pro_tier() -> None:
    user = User(id="user-1", email="test@example.com")
    subscription = {
        "id": "sub_123",
        "customer_id": "ctm_123",
        "status": "active",
        "started_at": "2026-01-01T00:00:00Z",
        "current_billing_period": {"ends_at": "2026-02-01T00:00:00Z"},
        "items": [{"price": {"id": "pri_monthly"}}],
    }

    with patch("src.services.subscription_sync.config") as mock_config:
        mock_config.paddle.price_pro_monthly = "pri_monthly"
        mock_config.paddle.price_pro_annual = "pri_annual"
        updated = apply_subscription_data_to_user(user, subscription)

    assert updated.tier == UserTier.PRO
    assert updated.paddle_subscription_id == "sub_123"
    assert updated.subscription_status == "active"
    assert user.tier == UserTier.FREE


def test_user_needs_subscription_sync_when_pro() -> None:
    user = User(
        id="user-1",
        email="test@example.com",
        tier=UserTier.PRO,
        paddle_subscription_id="sub_123",
        subscription_status="active",
    )
    assert user_needs_subscription_sync(user) is False


def test_user_needs_subscription_sync_when_pro_with_canceled_status() -> None:
    user = User(
        id="user-1",
        email="test@example.com",
        tier=UserTier.PRO,
        paddle_subscription_id="sub_123",
        subscription_status="canceled",
    )
    assert user_needs_subscription_sync(user) is True


def test_apply_subscription_data_to_user_downgrades_paused_tier() -> None:
    user = User(id="user-1", email="test@example.com", tier=UserTier.PRO)
    subscription = {
        "id": "sub_123",
        "customer_id": "ctm_123",
        "status": "paused",
        "started_at": "2026-01-01T00:00:00Z",
        "current_billing_period": {"ends_at": "2026-02-01T00:00:00Z"},
        "items": [{"price": {"id": "pri_monthly"}}],
    }

    with patch("src.services.subscription_sync.config") as mock_config:
        mock_config.paddle.price_pro_monthly = "pri_monthly"
        mock_config.paddle.price_pro_annual = "pri_annual"
        updated = apply_subscription_data_to_user(user, subscription)

    assert updated.tier == UserTier.FREE
    assert updated.subscription_status == "paused"


def test_user_needs_subscription_sync_when_free_with_subscription() -> None:
    user = User(
        id="user-1",
        email="test@example.com",
        tier=UserTier.FREE,
        paddle_subscription_id="sub_123",
        subscription_status="active",
    )
    assert user_needs_subscription_sync(user) is True
