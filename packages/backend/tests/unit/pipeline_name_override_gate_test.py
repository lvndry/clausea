"""Pipeline name-override gate: only auto-derived placeholders may be improved."""

from src.models.product import (
    NAME_SOURCE_AUTO_DOMAIN,
    NAME_SOURCE_AUTO_EXTRACTED,
    NAME_SOURCE_MANUAL,
)
from src.services.pipeline_service import _should_override_product_name


def test_auto_domain_placeholder_can_be_improved() -> None:
    assert _should_override_product_name("Bsky", NAME_SOURCE_AUTO_DOMAIN, "Bluesky") is True


def test_auto_domain_kept_when_no_brand_extracted() -> None:
    assert _should_override_product_name("Netflix", NAME_SOURCE_AUTO_DOMAIN, None) is False


def test_auto_domain_not_overwritten_with_same_name() -> None:
    assert _should_override_product_name("Netflix", NAME_SOURCE_AUTO_DOMAIN, "Netflix") is False


def test_manual_name_is_never_overridden() -> None:
    assert _should_override_product_name("Netflix", NAME_SOURCE_MANUAL, "Help Center") is False


def test_already_extracted_name_is_frozen() -> None:
    assert (
        _should_override_product_name("Bluesky", NAME_SOURCE_AUTO_EXTRACTED, "Bluesky Blog")
        is False
    )


def test_legacy_none_source_is_treated_as_improvable() -> None:
    assert _should_override_product_name("Openai", None, "OpenAI") is True
