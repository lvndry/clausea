from src.models.document import CORE_DOC_TYPES, Document
from src.models.user import UserTier
from src.routes.products import _can_access_document
from src.services.document_service import DocumentService


def _make_document(doc_type: str) -> Document:
    return Document(
        url=f"https://example.com/{doc_type}",
        title=doc_type,
        product_id="prod-1",
        doc_type=doc_type,  # type: ignore[arg-type]
        markdown="text",
        text="text",
    )


def test_core_doc_types_include_gdpr_policy() -> None:
    assert "gdpr_policy" in CORE_DOC_TYPES


def test_assign_tier_relevance_marks_core_docs() -> None:
    doc = _make_document("privacy_policy")
    DocumentService._assign_tier_relevance(doc)
    assert doc.tier_relevance == "core"


def test_assign_tier_relevance_marks_extended_docs() -> None:
    doc = _make_document("data_processing_agreement")
    DocumentService._assign_tier_relevance(doc)
    assert doc.tier_relevance == "extended"


def test_can_access_document_for_pro_user() -> None:
    assert _can_access_document(
        tier=UserTier.PRO,
        doc_type="data_processing_agreement",
        tier_relevance="extended",
    )


def test_can_access_document_for_free_user_core_by_type() -> None:
    assert _can_access_document(
        tier=UserTier.FREE,
        doc_type="terms_of_service",
        tier_relevance="extended",
    )


def test_cannot_access_document_for_free_user_extended() -> None:
    assert not _can_access_document(
        tier=UserTier.FREE,
        doc_type="data_processing_agreement",
        tier_relevance="extended",
    )
