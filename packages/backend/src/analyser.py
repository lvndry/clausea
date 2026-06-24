"""Document analysis module — evidence-first, deep analysis of policy documents.

Flow per document:
  1. extract_document_facts()  — structured evidence-backed extraction (chunked, parallel).
  2. analyse_document()        — unified deep analysis from extraction (one LLM call).

Flow for product overview (powers cached JSON on `/products/{slug}` in the app):
  3. generate_product_overview() — LLM synthesis from CORE documents only; saved via ProductService.
     This is separate from chat: the product page does not run embedding search to render the overview.
"""

import asyncio
import hashlib
import json
import re
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from typing import Any, Literal, NamedTuple

from dotenv import load_dotenv
from motor.core import AgnosticDatabase
from pymongo.errors import ConnectionFailure

from src.core.logging import get_logger
from src.llm import (
    MODEL_PRIORITY,
    SupportedModel,
    _extract_json_from_response,
    acompletion_with_fallback,
)
from src.models.document import (
    BusinessImpact,
    BusinessImpactAssessment,
    ComplianceBreakdown,
    ConsumerCase,
    ConsumerExplainer,
    ContractClauseReview,
    CrossDocumentAnalysis,
    DataProcessingProfile,
    DocType,
    Document,
    DocumentAnalysis,
    DocumentAnalysisScores,
    DocumentDeepAnalysis,
    DocumentExtraction,
    DocumentRiskBreakdown,
    DocumentSummary,
    DPIATriggerAssessment,
    IndividualImpact,
    InsightCategory,
    MetaSummary,
    MetaSummaryScores,
    PrivacySignals,
    ProcurementDecision,
    ProductContradiction,
    ProductDeepAnalysis,
    RegulationArticleBreakdown,
    RemediationItem,
    RiskRegisterItem,
    SecurityPosture,
    SourceCitation,
    TopicStanceBreakdown,
    TopicSupportCitation,
    WorkforceDataAssessment,
)
from src.prompts.analysis_prompts import (
    COMPLIANCE_ASSESSMENT_SYSTEM_PROMPT,
    COMPLIANCE_ASSESSMENT_USER_TEMPLATE,
    CONSUMER_EXPLAINER_ROLLUP_USER_TEMPLATE,
    CONSUMER_EXPLAINER_SYSTEM_PROMPT,
    CONSUMER_EXPLAINER_USER_TEMPLATE,
    DOCUMENT_ANALYSIS_PROMPT,
    OVERVIEW_CORE_DOC_TYPES,
    PRODUCT_DEEP_ANALYSIS_PROMPT,
    PRODUCT_OVERVIEW_PROMPT,
)
from src.repositories.document_repository import DocumentRepository
from src.services.document_service import DocumentService
from src.services.evidence_relevance import TOPIC_CITATION_LIMIT
from src.services.extraction_service import extract_document_facts
from src.services.product_rollup_service import ProductRollupService
from src.services.product_service import ProductService
from src.services.term_materiality_classifier import filter_danger_strings_llm
from src.services.topic_report_service import build_product_topic_report
from src.services.topic_stance_service import compose_product_risk_from_topics
from src.services.watch_out_calibration import calibrate_consumer_explainer
from src.utils.cancellation import CancellationToken
from src.utils.grading import (
    aggregate_dimension_grades,
    clamp_grade,
    coerce_grade,
    grade_to_risk_score,
    grade_to_verdict,
)
from src.utils.llm_usage import UsageTracker, log_usage_summary, usage_tracking
from src.utils.topic_copy import recommended_action_for, why_it_matters_for

load_dotenv()
logger = get_logger(__name__)

_ANALYSIS_PRIMARY: list[SupportedModel] = MODEL_PRIORITY
_OVERVIEW_PRIORITY: list[SupportedModel] = MODEL_PRIORITY


def _analysis_validator(content: str) -> bool:
    try:
        data = json.loads(content)
        if not isinstance(data, dict):
            return False
        if not isinstance(data.get("summary"), str) or not data["summary"].strip():
            return False
        grade = data.get("grade")
        if not isinstance(grade, str) or grade.strip().upper()[:1] not in {"A", "B", "C", "D", "E"}:
            return False
        scores = data.get("scores")
        if not isinstance(scores, dict) or not scores:
            return False
        for value in scores.values():
            if not isinstance(value, dict):
                return False
            dim_grade = value.get("grade")
            justification = value.get("justification")
            if not isinstance(dim_grade, str) or dim_grade.strip().upper()[:1] not in {
                "A",
                "B",
                "C",
                "D",
                "E",
            }:
                return False
            if not isinstance(justification, str) or not justification.strip():
                return False
        return True
    except (json.JSONDecodeError, AttributeError):
        return False


ProgressCallback = Callable[[int, int, Document], Awaitable[None] | None]

# A no-argument liveness ping fired at sub-step boundaries during long synthesis so the
# pipeline can bump the job heartbeat. Carries no payload — its only job is "still alive".
HeartbeatCallback = Callable[[], Awaitable[None] | None]


class AnalysisResult(NamedTuple):
    """Return value from :func:`analyse_product_documents`.

    Attributes:
        documents: Every policy document for the product (analyzed or skipped).
        analyses_skipped: Count of documents whose LLM analysis was reused from
            a prior run because content had not changed since the last extraction.
    """

    documents: list[Document]
    analyses_skipped: int


async def _maybe_await(result: Awaitable[None] | None) -> None:
    if asyncio.iscoroutine(result):
        await result


async def _stamp_analysis_error(
    db: AgnosticDatabase, document_svc: DocumentService, doc: Document
) -> None:
    """Persist ``doc.analysis_error`` so a dropped analysis is visible, not silent.

    Best-effort: a failure to write the marker must not mask the original analysis
    failure, so write errors are swallowed.
    """
    try:
        await document_svc.update_document(db, doc, invalidate_product_overview=False)
    except ConnectionFailure:
        raise
    except Exception as exc:
        logger.error(f"could not stamp analysis_error for document {doc.id}: {exc}")


def _analysis_up_to_date(doc: Document) -> bool:
    """Return True when the document has valid analysis for its current content.

    Checks that:
    1. The document already has analysis (was analyzed in a prior run).
    2. The stored extraction was built from the same content currently in the DB
       (source_content_hash matches the hash used by the extraction service).

    Uses the same SHA-256 hash function the extraction service uses
    (_compute_document_hash = SHA256(text + doc_type)) so the comparison is
    consistent with the extraction-layer cache.
    """
    if doc.analysis is None:
        return False
    if doc.extraction is None:
        return False
    return doc.extraction.source_content_hash == _compute_document_hash(doc)


async def analyse_product_documents(
    db: AgnosticDatabase,
    product_slug: str,
    document_svc: DocumentService,
    cancellation_token: CancellationToken | None = None,
    progress_callback: ProgressCallback | None = None,
    force_reanalyze: bool = False,
    heartbeat_callback: HeartbeatCallback | None = None,
) -> AnalysisResult:
    """Analyse all documents for a product concurrently (up to 3 at once).

    Each document analysis itself runs 4 parallel extraction clusters, so capping at 3
    concurrent documents balances throughput against LLM rate limits.

    Args:
        force_reanalyze: When True, bypass the content-hash cache and re-run LLM
            analysis on every document regardless of whether findings already exist.
            Defaults to False (skip-by-default behaviour).

    Returns:
        An :class:`AnalysisResult` named tuple containing the list of documents and
        the count of analyses that were reused without an LLM call.
    """
    token = cancellation_token or CancellationToken()
    all_documents: list[Document] = await document_svc.get_product_documents_by_slug(
        db, product_slug
    )
    # Only analyse classified policy documents — "other" means the classifier could not
    # assign a policy type, so deep analysis would produce noise rather than signal.
    documents = [d for d in all_documents if d.doc_type != "other"]
    skipped = len(all_documents) - len(documents)
    if skipped:
        logger.info(f"Skipping {skipped} 'other' documents for {product_slug}")
    total_docs: int = len(documents)
    logger.info(f"Analysing {total_docs} documents for {product_slug} (up to 3 concurrently)")

    sem = asyncio.Semaphore(3)

    failed_doc_ids: list[str] = []
    analyses_skipped = 0

    async def _analyse_one(index: int, doc: Document) -> None:
        nonlocal analyses_skipped
        await token.check_cancellation()
        async with sem:
            # Skip LLM re-analysis when findings already exist for this document
            # and the document content has not changed since the last analysis run.
            if not force_reanalyze and _analysis_up_to_date(doc):
                analyses_skipped += 1
                logger.info(
                    f"⏭ Skipping re-analysis for document {doc.id} ({doc.url}) — "
                    "existing analysis is up-to-date (content unchanged)"
                )
                return

            logger.info(f"Processing document {index}/{total_docs}: {doc.title}")
            if progress_callback:
                await _maybe_await(progress_callback(index, total_docs, doc))
            try:
                analysis = await analyse_document(
                    doc, cancellation_token=token, heartbeat_callback=heartbeat_callback
                )
                if analysis:
                    doc.analysis = analysis
                    doc.analysis_error = None
                    # Persist the full document first so the extraction and analysis
                    # metadata stamps set by analyse_document land alongside the body.
                    await document_svc.update_document(db, doc, invalidate_product_overview=False)
                    # Then persist analysis through the dedicated surgical path so the
                    # field is written with its own $set and cannot be silently dropped
                    # by a full-document rewrite. Confirm the write actually landed —
                    # an unpersisted analysis must surface as a failure, not be masked
                    # by the in-memory doc.analysis that the overview stage counts.
                    persisted = await document_svc.update_document_analysis(db, doc.id, analysis)
                    if not persisted:
                        doc.analysis = None
                        doc.analysis_error = "analysis generated but database write did not persist"
                        await _stamp_analysis_error(db, document_svc, doc)
                        failed_doc_ids.append(doc.id)
                        logger.error(
                            f"✗ Analysis for document {doc.id} ({doc.url}) was generated "
                            "but the database write did not persist it (update_analysis "
                            "reported no modification)."
                        )
                    else:
                        logger.info(f"✓ Stored analysis for document {doc.id}")
                else:
                    doc.analysis_error = "analyse_document returned no result after retries"
                    await _stamp_analysis_error(db, document_svc, doc)
                    failed_doc_ids.append(doc.id)
                    logger.warning(f"✗ Failed to generate analysis for document {doc.id}")
            except asyncio.CancelledError:
                logger.info(f"Summarization cancelled at document {index}/{total_docs}")
                raise
            except Exception as exc:
                # Per-document failure isolation: one bad document must not block
                # the rest of the product from getting its overview. Log loudly so
                # the failure is visible to operators, but allow sibling tasks to
                # complete. The overview stage downstream filters by doc.analysis,
                # so this doc simply contributes nothing rather than poisoning the
                # whole product.
                failed_doc_ids.append(doc.id)
                doc.analysis_error = f"{exc.__class__.__name__}: {exc}"[:500]
                await _stamp_analysis_error(db, document_svc, doc)
                logger.error(
                    f"✗ Document analysis raised for {doc.id} ({doc.url}): "
                    f"{exc.__class__.__name__}: {exc}",
                    exc_info=True,
                )

    # return_exceptions=True so a sibling raise (e.g. CancelledError) doesn't
    # mask the in-flight successful ones. Per-document failures are already
    # caught inside _analyse_one, so anything that escapes to gather is either
    # cancellation or a harness bug (cancellation check / progress callback) —
    # re-raise both rather than swallowing them.
    results = await asyncio.gather(
        *[_analyse_one(i, doc) for i, doc in enumerate(documents, 1)],
        return_exceptions=True,
    )
    for result in results:
        if isinstance(result, BaseException):
            raise result

    succeeded = total_docs - len(failed_doc_ids) - analyses_skipped
    if failed_doc_ids:
        logger.warning(
            f"⚠ Analysed {succeeded}/{total_docs} documents for {product_slug}; "
            f"{len(failed_doc_ids)} failed, {analyses_skipped} reused (unchanged): "
            f"{failed_doc_ids}"
        )
    else:
        logger.info(
            f"✓ Analysed {product_slug}: {succeeded} new/updated, "
            f"{analyses_skipped} reused (content unchanged), 0 failed"
        )
    return AnalysisResult(documents=documents, analyses_skipped=analyses_skipped)


def _compute_document_hash(document: Document) -> str:
    """Compute a hash for the document content to enable caching."""
    content = f"{document.markdown}{document.doc_type}"
    return hashlib.sha256(content.encode()).hexdigest()


def _compute_document_signature(documents: list[Document]) -> str:
    """
    Compute a signature from all document content hashes.

    This signature is used to detect when any document in a product has changed,
    which should invalidate the cached meta-summary.

    Args:
        documents: List of documents for a product

    Returns:
        SHA256 hash of sorted document content hashes
    """
    # Get all document hashes (use content_hash from metadata if available, otherwise compute)
    hashes = []
    for doc in documents:
        if doc.metadata and "content_hash" in doc.metadata:
            hashes.append(doc.metadata["content_hash"])
        else:
            # If no hash stored, compute it (but this shouldn't happen for analyzed docs)
            hashes.append(_compute_document_hash(doc))

    # Sort for consistency (order shouldn't matter)
    hashes.sort()

    # Combine and hash
    combined = "|".join(hashes)
    return hashlib.sha256(combined.encode()).hexdigest()


def _calculate_overview_risk_score(scores: MetaSummaryScores) -> int | None:
    """Derive product headline risk from LLM-assessed overview dimension grades."""
    return _calculate_risk_score(
        {
            key: DocumentAnalysisScores(
                grade=getattr(scores, key).grade,
                justification=getattr(scores, key).justification,
            )
            for key in (
                "transparency",
                "data_collection_scope",
                "user_control",
                "third_party_sharing",
            )
        }
    )


def _reconcile_meta_summary_risk(meta_summary: MetaSummary) -> None:
    """Set headline grade, verdict, and deprecated risk_score from evidence.

    The LLM overall grade is clamped to within one letter of the
    dimension-derived grade to counter the LLM's systematic negativity bias
    (44/45 disagreements with dimensions were more negative in production).
    Verdict is derived directly from the final grade so they can never
    contradict each other on the card.
    """
    llm_grade = coerce_grade(meta_summary.grade) if meta_summary.grade else None
    derived_grade = aggregate_dimension_grades(
        {
            key: getattr(meta_summary.scores, key).grade
            for key in (
                "transparency",
                "data_collection_scope",
                "user_control",
                "third_party_sharing",
            )
        }
    )

    if llm_grade and derived_grade:
        final_grade = clamp_grade(llm_grade, derived_grade, max_delta=1)
        if final_grade != llm_grade:
            logger.info(
                "Clamped overview grade from LLM %s to %s (dimension-derived: %s)",
                llm_grade,
                final_grade,
                derived_grade,
            )
    else:
        final_grade = llm_grade or derived_grade

    if final_grade is None:
        meta_summary.risk_score = None
        meta_summary.verdict = None
        meta_summary.grade = None
        return

    meta_summary.grade = final_grade
    meta_summary.verdict = grade_to_verdict(final_grade)
    meta_summary.risk_score = grade_to_risk_score(final_grade)


def _calculate_risk_score(scores: dict[str, DocumentAnalysisScores]) -> int | None:
    """Map weighted dimension letter grades to an optional 0–10 risk score."""
    grade = aggregate_dimension_grades({key: value.grade for key, value in scores.items()})
    if grade is None:
        return None
    return grade_to_risk_score(grade)


def _calculate_verdict(
    risk_score: int,
) -> Literal["very_user_friendly", "user_friendly", "moderate", "pervasive", "very_pervasive"]:
    """Calculate privacy friendliness level from risk score.

    Lower risk scores = more user-friendly privacy practices.
    Higher risk scores = more pervasive data collection and sharing.
    """
    if risk_score <= 2:
        return "very_user_friendly"
    elif risk_score <= 4:
        return "user_friendly"
    elif risk_score <= 6:
        return "moderate"
    elif risk_score <= 8:
        return "pervasive"
    else:
        return "very_pervasive"


def _calculate_grade(risk_score: int) -> Literal["A", "B", "C", "D", "E"]:
    if risk_score <= 2:
        return "A"
    if risk_score <= 4:
        return "B"
    if risk_score <= 6:
        return "C"
    if risk_score <= 8:
        return "D"
    return "E"


def _apply_positive_risk_adjustment(risk_score: int, meta_summary: MetaSummary) -> int:
    """Reduce headline risk when documented protections outweigh thin concerns."""
    adjustment = 0
    benefits = meta_summary.benefits or []
    if len(benefits) >= 2:
        adjustment += 1
    stances = meta_summary.topic_stances or []
    low_risk_topics = sum(
        1 for stance in stances if stance.stance == "low_risk" and stance.status == "found"
    )
    if low_risk_topics >= 3:
        adjustment += 1
    return max(0, risk_score - adjustment)


def _apply_signal_floors(risk_score: int, signals: PrivacySignals | None) -> int:
    if signals is None:
        return risk_score
    floor = risk_score
    if signals.sells_data == "yes" or signals.ai_training_on_user_data == "yes":
        floor = max(floor, 6)
    if signals.children_data_collection == "yes":
        floor = max(floor, 7)
    critical_count = sum(
        [
            signals.sells_data == "yes",
            signals.ai_training_on_user_data == "yes",
            signals.children_data_collection == "yes",
            signals.cross_site_tracking == "yes",
        ]
    )
    if critical_count >= 2:
        floor = max(floor, 8)
    return floor


_TOPIC_WHY_IT_MATTERS: dict[str, str] = {}
_TOPIC_RECOMMENDED_ACTIONS: dict[str, str] = {}


def _truncate_text(value: str | None, limit: int = 220) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1].rstrip()}..."


def _topic_supporting_citations(topic: Any) -> list[TopicSupportCitation]:
    selected: list[TopicSupportCitation] = []
    seen: set[tuple[str, str]] = set()
    for finding in topic.findings:
        for citation in finding.citations or []:
            quote = getattr(citation, "quote", None)
            if not quote:
                continue
            document_id = getattr(citation, "document_id", "")
            key = (document_id, str(quote))
            if key in seen:
                continue
            seen.add(key)
            selected.append(
                TopicSupportCitation(
                    document_id=document_id,
                    document_title=getattr(citation, "document_title", None),
                    document_url=getattr(citation, "document_url", None),
                    quote=str(quote),
                    section_title=getattr(citation, "section_title", None),
                    verified=bool(getattr(citation, "verified", True)),
                )
            )
            if len(selected) >= TOPIC_CITATION_LIMIT:
                return selected
    for conflict in topic.conflicts:
        for citation in conflict.citations or []:
            quote = getattr(citation, "quote", None)
            if not quote:
                continue
            document_id = getattr(citation, "document_id", "")
            key = (document_id, str(quote))
            if key in seen:
                continue
            seen.add(key)
            selected.append(
                TopicSupportCitation(
                    document_id=document_id,
                    document_title=getattr(citation, "document_title", None),
                    document_url=getattr(citation, "document_url", None),
                    quote=str(quote),
                    section_title=getattr(citation, "section_title", None),
                    verified=bool(getattr(citation, "verified", True)),
                )
            )
            if len(selected) >= TOPIC_CITATION_LIMIT:
                return selected
    return selected


_PROTECTIVE_HEADLINE_TOPICS: frozenset[str] = frozenset(
    {"benefits", "security", "user_rights", "breach_notification", "data_sale", "ai_training"}
)
_PROTECTIVE_VALUE_MARKERS: tuple[str, ...] = (
    "sells_data: no",
    "does not sell",
    "do not sell",
    "not sell",
    "encrypt",
    "no ai training",
    "not used for training",
    "does not use",
    "opt out",
    "delete your",
    "data deletion",
)


def _is_protective_finding_value(topic: str, value: str | None) -> bool:
    normalized = (value or "").strip().lower()
    if not normalized:
        return False
    if topic in _PROTECTIVE_HEADLINE_TOPICS:
        if topic in {"benefits", "security", "user_rights", "breach_notification"}:
            return True
        if topic == "data_sale" and (
            re.search(r"\bno\b", normalized) is not None or "not sell" in normalized
        ):
            return True
        if topic == "ai_training" and (
            re.search(r"\bno\b", normalized) is not None
            or any(marker in normalized for marker in ("not train", "does not use", "opt out"))
        ):
            return True
    return any(marker in normalized for marker in _PROTECTIVE_VALUE_MARKERS)


def _headline_finding_for_topic(topic: Any) -> Any | None:
    findings = list(getattr(topic, "findings", []) or [])
    if not findings:
        return None
    stance = str(getattr(topic, "stance", "") or "")
    topic_name = str(getattr(topic, "topic", "") or "")
    if stance == "low_risk":
        for finding in findings:
            if _is_protective_finding_value(topic_name, getattr(finding, "value", None)):
                return finding
    return findings[0]


def _topic_why_it_matters(topic: str, status: str, stance: str, conflict_count: int) -> str:
    return why_it_matters_for(topic, status, stance, conflict_count)


def _topic_recommended_action(topic: str, status: str, stance: str) -> str:
    return recommended_action_for(topic, status, stance)


# Doc types that must never influence the product risk score or deep analysis LLM prompt.
# "other" means the classifier could not assign a policy type; community_guidelines and
# copyright_policy address editorial/IP rules rather than data/privacy risk.
_PRODUCT_OVERVIEW_EXCLUDED_DOC_TYPES: frozenset[str] = frozenset(
    {"other", "community_guidelines", "copyright_policy"}
)

# Weights for product-level risk: privacy/cookie/GDPR documents drive the headline
# score more than terms-of-service legal boilerplate, so one liability-heavy ToS
# does not mask a permissive privacy policy (or vice versa for privacy-first apps).
_PRODUCT_OVERVIEW_DOC_RISK_WEIGHTS: dict[DocType, float] = {
    "privacy_policy": 3.0,
    "cookie_policy": 1.5,
    "gdpr_policy": 1.5,
    "security_policy": 1.5,
    "data_processing_agreement": 1.0,
    "children_privacy_policy": 1.0,
    "terms_of_service": 1.0,
    "terms_of_use": 1.0,
    "terms_and_conditions": 1.0,
}


def _weighted_product_risk_score(docs: list[Document]) -> int | None:
    """Mean of per-document risk scores, weighted toward privacy-centric documents."""
    weighted_sum = 0.0
    weight_total = 0.0
    for doc in docs:
        if doc.doc_type in _PRODUCT_OVERVIEW_EXCLUDED_DOC_TYPES:
            continue
        if not doc.analysis or doc.analysis.risk_score is None:
            continue
        w = _PRODUCT_OVERVIEW_DOC_RISK_WEIGHTS.get(doc.doc_type, 1.0)
        weighted_sum += doc.analysis.risk_score * w
        weight_total += w
    if weight_total <= 0:
        return None
    return max(0, min(10, round(weighted_sum / weight_total)))


def _merge_legacy_dimension_justifications(
    parsed_dict: dict[str, Any],
) -> None:
    """Convert legacy dimension_justifications-only LLM output to grade scores."""
    legacy = parsed_dict.pop("dimension_justifications", None)
    if not isinstance(legacy, dict):
        return
    scores = parsed_dict.setdefault("scores", {})
    if not isinstance(scores, dict):
        scores = {}
        parsed_dict["scores"] = scores
    for key, justification in legacy.items():
        if key in scores and isinstance(scores[key], dict):
            continue
        if isinstance(justification, str) and justification.strip():
            scores[key] = {"grade": "C", "justification": justification.strip()}


def _ensure_required_scores(parsed: DocumentAnalysis) -> DocumentAnalysis:
    """
    Validate LLM dimension grades and derive grade, verdict, and deprecated risk_score.

    The LLM overall ``grade`` is clamped to within one letter of the
    dimension-derived grade to counter the negativity bias documented at
    product-level.  ``verdict`` derives from the final ``grade`` so they
    never contradict.  ``risk_score`` is kept for legacy consumers only.
    """
    cleaned: dict[str, DocumentAnalysisScores] = {}
    for score_name, score_obj in parsed.scores.items():
        justification = (score_obj.justification or "").strip()
        if score_obj.grade and justification:
            cleaned[score_name] = score_obj

    parsed.scores = cleaned

    llm_grade = coerce_grade(parsed.grade) if parsed.grade else None
    derived_grade = aggregate_dimension_grades({key: value.grade for key, value in cleaned.items()})

    if llm_grade and derived_grade:
        final_grade = clamp_grade(llm_grade, derived_grade, max_delta=1)
    else:
        final_grade = llm_grade or derived_grade

    if final_grade is None:
        parsed.risk_score = None
        parsed.verdict = None
        parsed.grade = None
        return parsed

    parsed.grade = final_grade
    parsed.verdict = grade_to_verdict(final_grade)
    parsed.risk_score = grade_to_risk_score(final_grade)
    return parsed


def _attach_keypoint_evidence(
    analysis: DocumentAnalysis,
    extraction_json: dict[str, Any] | None,
) -> None:
    """Best-effort attach evidence spans from extraction to keypoints.

    This is intentionally heuristic: it improves auditability immediately without
    requiring the LLM to emit citations. The UI can still rely on `Document.extraction`
    for fully structured, evidence-backed facts.
    """
    if not analysis.keypoints or not extraction_json:
        return

    # Build a small pool of evidence spans keyed by a normalized "value".
    evidence_pool: list[tuple[str, list[dict[str, Any]]]] = []
    for key in [
        "data_collected",
        "data_purposes",
        "retention_policies",
        "security_measures",
        "cookies_and_trackers",
        "third_party_details",
        "international_transfers",
        "government_access",
        "corporate_family_sharing",
        "user_rights",
        "consent_mechanisms",
        "account_lifecycle",
        "ai_usage",
        "liability",
        "dispute_resolution",
        "content_ownership",
        "scope_expansion",
        "indemnification",
        "termination_consequences",
        "dangers",
        "benefits",
        "recommended_actions",
    ]:
        items = extraction_json.get(key) or []
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            value = str(
                item.get("value")
                or item.get("description")
                or item.get("data_type")
                or item.get("right_type")
                or item.get("recipient")
                or item.get("destination")
                or item.get("name_or_type")
                or item.get("scope")
                or ""
            ).strip()
            evidence = item.get("evidence") or []
            if value and isinstance(evidence, list) and evidence:
                evidence_pool.append((value.lower(), evidence))

    if not evidence_pool:
        return

    keypoints_with_evidence = []
    for kp in analysis.keypoints:
        kp_str = str(kp or "").strip()
        if not kp_str:
            continue
        kp_lower = kp_str.lower()

        matched_evidence: list[dict[str, Any]] = []
        for value_norm, evidence in evidence_pool:
            if value_norm and value_norm in kp_lower:
                matched_evidence.extend(evidence)
                if len(matched_evidence) >= 3:
                    break

        # Keep a small number of spans to avoid huge payloads
        matched_evidence = matched_evidence[:3]

        try:
            from src.models.document import EvidenceSpan, KeypointWithEvidence

            keypoints_with_evidence.append(
                KeypointWithEvidence(
                    keypoint=kp_str,
                    evidence=[
                        EvidenceSpan.model_validate(e, strict=False) for e in matched_evidence
                    ],
                )
            )
        except Exception:
            # Never break analysis creation due to evidence attachment
            continue

    if keypoints_with_evidence:
        analysis.keypoints_with_evidence = keypoints_with_evidence


def _extract_last_updated_from_metadata(metadata: dict[str, Any] | None) -> datetime | None:
    """
    Extract and parse last_updated datetime from document metadata.

    Args:
        metadata: Document metadata dictionary

    Returns:
        Parsed datetime object or None if not available or unparseable
    """
    if not metadata or "last_updated" not in metadata:
        return None

    last_updated_value = metadata["last_updated"]
    if isinstance(last_updated_value, datetime):
        return last_updated_value
    elif isinstance(last_updated_value, str):
        # Try common date formats
        date_formats = [
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%m/%d/%Y",
            "%d/%m/%Y",
        ]
        for fmt in date_formats:
            try:
                return datetime.strptime(last_updated_value, fmt)
            except ValueError:
                continue
        logger.debug(f"Could not parse last_updated from metadata: {last_updated_value}")
    return None


def _attach_deep_fields(analysis: DocumentAnalysis, data: dict[str, Any]) -> None:
    """Parse deep analysis fields (critical_clauses, risk_breakdown, key_sections)
    from the unified analysis response dict and attach them to the analysis object.

    Best-effort: individual parsing failures are logged but do not abort the analysis.
    """
    from src.models.document import CriticalClause, DocumentSection

    risk_breakdown_raw = data.get("document_risk_breakdown", {})
    if isinstance(risk_breakdown_raw, dict):
        if "overall_risk" not in risk_breakdown_raw and analysis.risk_score is not None:
            risk_breakdown_raw["overall_risk"] = analysis.risk_score
        try:
            analysis.document_risk_breakdown = DocumentRiskBreakdown(**risk_breakdown_raw)
        except Exception as e:
            logger.warning(f"Failed to parse document_risk_breakdown: {e}")

    raw_clauses = data.get("critical_clauses", [])
    if isinstance(raw_clauses, list):
        try:
            parsed_clauses = []
            for c in raw_clauses:
                if not isinstance(c, dict):
                    continue
                # Backfill analysis from plain_english for backward compat
                if not c.get("analysis") and c.get("plain_english"):
                    c["analysis"] = c["plain_english"]
                parsed_clauses.append(CriticalClause.model_validate(c))
            analysis.critical_clauses = parsed_clauses
        except Exception as e:
            logger.warning(f"Failed to parse critical_clauses: {e}")

    analysis.analysis_completeness = data.get("analysis_completeness", "full")
    raw_gaps = data.get("coverage_gaps", [])
    if isinstance(raw_gaps, list):
        analysis.coverage_gaps = [str(g) for g in raw_gaps if g]

    raw_sections = data.get("key_sections", [])
    if isinstance(raw_sections, list):
        try:
            analysis.key_sections = [
                DocumentSection.model_validate(s) for s in raw_sections if isinstance(s, dict)
            ]
        except Exception as e:
            logger.warning(f"Failed to parse key_sections: {e}")

    if analysis.document_risk_breakdown is not None:
        br = analysis.document_risk_breakdown
        nested_updates: dict[str, Any] = {}
        if not (br.applicability and str(br.applicability).strip()) and analysis.applicability:
            nested_updates["applicability"] = analysis.applicability
        if not br.missing_information and analysis.coverage_gaps:
            nested_updates["missing_information"] = list(analysis.coverage_gaps)
        if nested_updates:
            analysis.document_risk_breakdown = br.model_copy(update=nested_updates)


async def analyse_document(
    document: Document,
    use_cache: bool = True,
    max_retries: int = 3,
    cancellation_token: CancellationToken | None = None,
    heartbeat_callback: HeartbeatCallback | None = None,
) -> DocumentAnalysis | None:
    """
    Summarize a document with caching, retry logic, and optimized model selection.

    Args:
        document: The document to summarize
        use_cache: Whether to check for cached analysis
        max_retries: Maximum number of retry attempts
        cancellation_token: Optional cancellation token for interrupting the operation
        heartbeat_callback: Optional liveness ping fired between retry attempts so the
            caller can keep a pipeline job alive during long LLM backoff sequences.

    Returns:
        DocumentAnalysis or None if summarization fails or the document has no text

    Raises:
        asyncio.CancelledError: If cancellation is requested
    """
    # For HTTP requests, create a fresh token if none provided
    # The global token is for signal-based cancellation (Ctrl+C) and may be in a cancelled state
    if cancellation_token is None:
        token = CancellationToken()
    else:
        token = cancellation_token

    if not (document.markdown or "").strip():
        logger.info(f"Skipping analysis for document {document.id}: no content")
        return None

    # Check cache if enabled and document already has analysis
    if use_cache and document.analysis:
        # Compute current document hash
        current_hash = _compute_document_hash(document)

        # Get stored hash from metadata (if exists)
        stored_hash = document.metadata.get("content_hash") if document.metadata else None

        # Only use cached analysis if hash matches (ensures document hasn't changed)
        if stored_hash and stored_hash == current_hash:
            logger.debug(
                f"Using cached analysis for document {document.id} "
                f"(hash match: {current_hash[:8]}...)"
            )
            return document.analysis
        else:
            if stored_hash:
                logger.info(
                    f"Document {document.id} content changed "
                    f"(hash mismatch: stored {stored_hash[:8]}... vs current {current_hash[:8]}...). "
                    "Re-analyzing document."
                )
            else:
                logger.debug(
                    f"No stored hash found for document {document.id}. "
                    "Re-analyzing to generate fresh analysis."
                )

    # Phase 1: Extract structured facts (chunked, 4 parallel clusters per chunk).
    # Phase 2: Deep analysis from extracted facts (one unified call).
    # Fallback: raw text if extraction fails unexpectedly.
    extracted_prompt: str | None = None
    extraction_for_evidence: dict[str, Any] | None = None
    extraction: DocumentExtraction | None = None

    try:
        await token.check_cancellation()
        extraction = await extract_document_facts(
            document,
            use_cache=True,
            cancellation_token=token,
        )
        extraction_for_evidence = extraction.model_dump()

        # Extraction chunks the full document; analyse_document does not run without text.
        extracted_prompt = f"""Document Title: {document.title or "Not specified"}
Document Type: {document.doc_type}
Document URL: {document.url}
Document Regions: {document.regions}
Document Locale: {document.locale or "Not specified"}

Extraction completeness: FULL — the entire document was processed.

Rules:
- Use ONLY the extracted facts below. Do NOT add data types, purposes, rights, third parties, or claims not present in the extraction.
- If something is absent from the extraction, state "Not specified in document".
- Every critical clause quote must come from the extraction's evidence fields.

Extracted facts (evidence-backed JSON):
{extraction.model_dump_json()}""".strip()

    except Exception as e:
        logger.warning(
            f"Extraction failed for document {document.id}: {e}. Falling back to raw text."
        )
        extraction = None

    if extracted_prompt is not None:
        prompt = extracted_prompt
    else:
        # Fallback: raw markdown path (extraction unavailable)
        doc_markdown = document.markdown or ""
        max_chars = 200000

        if len(doc_markdown) > max_chars:
            logger.warning(
                f"Document {document.id} is very long ({len(doc_markdown)} chars), truncating for fallback path."
            )
            doc_markdown = (
                doc_markdown[: max_chars // 2]
                + "\n\n[... document truncated — set analysis_completeness to 'partial' ...]\n\n"
                + doc_markdown[-max_chars // 2 :]
            )

        prompt = f"""Document Title: {document.title or "Not specified"}
Document Type: {document.doc_type}
Document URL: {document.url}
Document Regions: {document.regions}
Document Locale: {document.locale or "Not specified"}

Extraction completeness: PARTIAL — structured extraction unavailable, analyzing raw content.
Set analysis_completeness to 'partial' in your response.

Document content:
{doc_markdown}""".strip()

    last_exception: Exception | None = None

    # Set up usage tracking for this document summarization
    usage_tracker = UsageTracker()
    tracker_callback = usage_tracker.create_tracker("analyse_document")

    for attempt in range(max_retries):
        # Check for cancellation before each retry attempt
        await token.check_cancellation()
        await _maybe_await(heartbeat_callback() if heartbeat_callback else None)

        try:
            logger.debug(f"Analysing document {document.id} (attempt {attempt + 1}/{max_retries}) ")

            async with usage_tracking(tracker_callback):
                # Wrap the LLM call in a cancellable task
                llm_task = asyncio.create_task(
                    acompletion_with_fallback(
                        messages=[
                            {"role": "system", "content": DOCUMENT_ANALYSIS_PROMPT},
                            {"role": "user", "content": prompt},
                        ],
                        model_priority=_ANALYSIS_PRIMARY,
                        validator=_analysis_validator,
                        response_format={"type": "json_object"},
                        temperature=0,
                        heartbeat_callback=heartbeat_callback,
                    )
                )

                # Wait for either completion or cancellation
                cancellation_task = asyncio.create_task(token.cancelled.wait())
                _, pending = await asyncio.wait(
                    [llm_task, cancellation_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # Cancel pending tasks
                for pending_task in pending:
                    pending_task.cancel()
                    try:
                        await pending_task
                    except asyncio.CancelledError:
                        pass

                # If cancellation was requested, cancel the LLM task
                if token.is_cancelled():
                    llm_task.cancel()
                    try:
                        await llm_task
                    except asyncio.CancelledError:
                        pass
                    raise asyncio.CancelledError("Document analysis cancelled")

                # Get the response
                response = await llm_task
                logger.info("analyse_document %s used model %s", document.id, response.model)

            choice = response.choices[0]
            if not hasattr(choice, "message"):
                raise ValueError("Unexpected response format: missing message attribute")
            message = choice.message  # type: ignore[attr-defined]
            if not message:
                raise ValueError("Unexpected response format: message is None")
            content = message.content  # type: ignore[attr-defined]
            if not content:
                raise ValueError("Empty response from LLM")

            # Parse and validate response
            try:
                parsed_dict = json.loads(content)
                _merge_legacy_dimension_justifications(parsed_dict)

                parsed: DocumentAnalysis = DocumentAnalysis.model_validate(
                    parsed_dict, strict=False
                )
                parsed = _ensure_required_scores(parsed)

                # Parse deep analysis fields (critical_clauses, risk_breakdown,
                # analysis_completeness, coverage_gaps) from the same response — deep is default.
                _attach_deep_fields(parsed, parsed_dict)

                # Attach evidence spans to keypoints when possible (best-effort)
                _attach_keypoint_evidence(parsed, extraction_for_evidence)

                # Store content hash in metadata for future cache validation
                content_hash = _compute_document_hash(document)

                document.metadata["content_hash"] = content_hash
                document.metadata["analysis_hash_stored_at"] = datetime.now().isoformat()

                logger.info(
                    f"Successfully analysed document {document.id} "
                    f"(hash: {content_hash[:8]}..., "
                    f"completeness: {parsed.analysis_completeness})"
                )

                # Log LLM usage for this document analysis (success case)
                summary, records = usage_tracker.consume_summary()
                log_usage_summary(
                    summary,
                    records,
                    context=f"document_{document.id}",
                    reason="success",
                    operation_type="analysis",
                    product_id=document.product_id,
                    document_id=document.id,
                    document_url=document.url,
                    document_title=document.title,
                )

                return parsed

            except Exception as parse_error:
                last_exception = parse_error
                logger.warning(
                    f"Failed to parse LLM response on attempt {attempt + 1}/{max_retries} "
                    f"for document {document.id}: {parse_error}"
                )
                # Do NOT return a fallback immediately — allow remaining retries to run.
                # The fallback is only built after all attempts are exhausted (below the loop).

        except asyncio.CancelledError:
            # Re-raise cancellation errors immediately
            logger.info(f"Document analysis cancelled for {document.id}")
            raise
        except Exception as e:
            last_exception = e
            logger.warning(
                f"Attempt {attempt + 1}/{max_retries} failed for document {document.id}: {str(e)}"
            )

            # Check for cancellation before retrying
            await token.check_cancellation()

            # Exponential backoff: wait before retry (except on last attempt)
            if attempt < max_retries - 1:
                wait_time = 2**attempt  # 1s, 2s, 4s...
                logger.debug(f"Waiting {wait_time}s before retry...")
                await _maybe_await(heartbeat_callback() if heartbeat_callback else None)
                # Use cancellable sleep
                try:
                    await asyncio.wait_for(
                        asyncio.sleep(wait_time),
                        timeout=wait_time,
                    )
                except asyncio.CancelledError:
                    raise
            continue

    # All retries exhausted — return None so the document is marked as unanalysed.
    # Callers log the failure and skip storage; the UI shows an explicit error state
    # rather than fabricated neutral scores.
    summary, records = usage_tracker.consume_summary()
    log_usage_summary(
        summary,
        records,
        context=f"document_{document.id}",
        reason="failed",
        operation_type="analysis",
        document_id=document.id,
        document_url=document.url,
        document_title=document.title,
    )

    logger.error(
        f"Failed to analyse document {document.id} after {max_retries} attempts: {last_exception}"
    )
    return None


# ---------------------------------------------------------------------------
# Consumer TOS-explainer (plain-English, end-user facing)
# ---------------------------------------------------------------------------


def _collect_extraction_citations(
    extraction: DocumentExtraction, document: Document | None = None
) -> list[SourceCitation]:
    """Collect every verbatim evidence quote with source document metadata.

    The validator uses these as the allow-list for explainer citations: an
    explainer quote is only kept (cited) when it is a substring of one of these.
    Source identity comes from stored extraction evidence and document metadata,
    never from the LLM response.
    """
    citations: list[SourceCitation] = []
    seen: set[tuple[str, str, int | None, int | None]] = set()

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            quote = node.get("quote")
            if isinstance(quote, str) and quote.strip():
                document_id = str(
                    node.get("document_id") or (document.id if document else "")
                ).strip()
                document_url = str(node.get("url") or (document.url if document else "")).strip()
                if document_id and document_url:
                    start_char = node.get("start_char")
                    end_char = node.get("end_char")
                    key = (
                        document_id,
                        quote.strip(),
                        start_char if isinstance(start_char, int) else None,
                        end_char if isinstance(end_char, int) else None,
                    )
                    if key not in seen:
                        seen.add(key)
                        citations.append(
                            SourceCitation(
                                document_id=document_id,
                                document_title=document.title if document else None,
                                document_type=str(document.doc_type) if document else None,
                                document_url=document_url,
                                quote=quote,
                                section_title=node.get("section_title")
                                if isinstance(node.get("section_title"), str)
                                else None,
                                start_char=start_char if isinstance(start_char, int) else None,
                                end_char=end_char if isinstance(end_char, int) else None,
                                content_hash=node.get("content_hash")
                                if isinstance(node.get("content_hash"), str)
                                else None,
                                verified=bool(node.get("verified", True)),
                            )
                        )
            for value in node.values():
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(extraction.model_dump())
    return citations


def _collect_extraction_quotes(extraction: DocumentExtraction) -> list[str]:
    """Backward-compatible quote-only allow-list for existing tests/callers."""
    return [citation.quote for citation in _collect_extraction_citations(extraction)]


def _match_source_citations(
    quote: str | None, allowed_citations: Sequence[SourceCitation]
) -> list[SourceCitation]:
    """Return every source citation whose verified quote contains ``quote``."""
    needle = (quote or "").strip()
    if not needle:
        return []
    matched: list[SourceCitation] = []
    seen: set[tuple[str, str]] = set()
    for citation in allowed_citations:
        if needle not in citation.quote:
            continue
        key = (citation.document_id, citation.quote)
        if key in seen:
            continue
        seen.add(key)
        matched.append(citation)
    return matched


def _citation_has_source_identity(citation: SourceCitation | None) -> bool:
    """True when a citation carries enough metadata for the UI source label."""
    if citation is None:
        return False
    if citation.document_title and citation.document_title.strip():
        return True
    if citation.document_type and citation.document_type.strip():
        return True
    return bool(citation.document_url and citation.document_url.strip())


def enrich_consumer_explainer_citations(
    explainer: ConsumerExplainer,
    documents: Sequence[Document],
) -> ConsumerExplainer:
    """Attach missing source citations for legacy stored explainers on read.

    Explainers generated before verified citations shipped may still carry
    ``quote_status="from_extraction"`` without a populated ``citation`` object.
    """
    allowed_citations: list[SourceCitation] = []
    for document in documents:
        extraction = document.extraction
        if extraction is None:
            continue
        allowed_citations.extend(_collect_extraction_citations(extraction, document))
    if not allowed_citations:
        return explainer

    def _attach(cases: Sequence[ConsumerCase]) -> None:
        for case in cases:
            if not case.quote or case.quote_status != "from_extraction":
                continue
            verified = [
                citation
                for citation in _match_source_citations(case.quote, allowed_citations)
                if citation.document_id != "unknown"
            ]
            if not verified:
                continue
            case.citations = verified
            if not _citation_has_source_identity(case.citation):
                case.citation = verified[0]

    _attach(explainer.watch_out_for)
    _attach(explainer.who_gets_your_data)
    _attach(explainer.what_they_collect)
    return explainer


def _strip_json_fences(content: str) -> str:
    """Drop leading/trailing markdown code fences weak models leak despite Rule 7."""
    text = content.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[: -len("```")]
    return text.strip()


def _validate_consumer_explainer(
    explainer: ConsumerExplainer,
    extraction: DocumentExtraction,
    document: Document | None = None,
) -> ConsumerExplainer:
    """Validate a per-document explainer against that document's extraction."""
    return _validate_consumer_explainer_quotes(
        explainer, _collect_extraction_citations(extraction, document)
    )


def _validate_consumer_explainer_quotes(
    explainer: ConsumerExplainer, allowed_quotes: Sequence[str | SourceCitation]
) -> ConsumerExplainer:
    """Server-side validator the finalized prompt explicitly depends on.

    1. De-cite any quote that is not a verbatim substring of some allowed
       extraction quote: set ``quote=None`` and ``quote_status="none"``. The
       finding is KEPT, only its citation is dropped. (For a product roll-up,
       ``allowed_quotes`` is the union across all of the product's documents.)
    2. Recompute ``critical_findings_count`` from the finding lists.
    3. Clamp ``grade`` server-side: >=1 critical -> at most D; >=2 -> at most E.
       The model's grade is never trusted on its own.
    """

    allowed_citations = [
        item
        if isinstance(item, SourceCitation)
        else SourceCitation(
            document_id="unknown",
            document_url="",
            quote=item,
            verified=False,
        )
        for item in allowed_quotes
        if isinstance(item, SourceCitation) or (isinstance(item, str) and item.strip())
    ]

    def _recite(cases: Sequence[ConsumerCase]) -> None:
        for case in cases:
            if not case.quote:
                case.quote = None
                case.quote_status = "none"
                case.citation = None
                case.citations = []
                continue
            matched = _match_source_citations(case.quote, allowed_citations)
            verified = [citation for citation in matched if citation.document_id != "unknown"]
            if verified:
                case.quote_status = "from_extraction"
                case.citations = verified
                case.citation = verified[0]
            else:
                case.quote = None
                case.quote_status = "none"
                case.citation = None
                case.citations = []

    _recite(explainer.watch_out_for)
    _recite(explainer.who_gets_your_data)
    _recite(explainer.what_they_collect)

    calibrate_consumer_explainer(explainer)

    critical_count = sum(
        1
        for case in (
            *explainer.watch_out_for,
            *explainer.who_gets_your_data,
            *explainer.what_they_collect,
        )
        if case.severity == "critical" or (case.classification or "").strip().lower() == "blocker"
    )
    explainer.critical_findings_count = critical_count

    grade_order = ["A", "B", "C", "D", "E"]
    if critical_count >= 2:
        floor = "E"
    elif critical_count == 1:
        floor = "D"
    else:
        floor = None

    if floor is not None:
        current_index = grade_order.index(explainer.grade) if explainer.grade in grade_order else 2
        floor_index = grade_order.index(floor)
        if current_index < floor_index:
            logger.info(
                "ConsumerExplainer grade clamp: %s -> %s (%d critical findings)",
                explainer.grade,
                floor,
                critical_count,
            )
            explainer.grade = floor
            explainer.grade_reason = (
                f"Grade adjusted to {floor}: {critical_count} critical "
                f"finding{'s' if critical_count != 1 else ''}."
            )
    elif critical_count == 0 and len(explainer.good_to_know or []) >= 2:
        current_index = grade_order.index(explainer.grade) if explainer.grade in grade_order else 2
        boost_index = max(0, current_index - 1)
        if boost_index < current_index:
            improved = grade_order[boost_index]
            logger.info(
                "ConsumerExplainer grade boost: %s -> %s (%d good_to_know items)",
                explainer.grade,
                improved,
                len(explainer.good_to_know or []),
            )
            explainer.grade = improved
            if not explainer.grade_reason:
                explainer.grade_reason = (
                    "Grade reflects documented protections described in the policies."
                )

    return explainer


async def generate_consumer_explainer(
    document: Document,
    *,
    cancellation_token: CancellationToken | None = None,
    max_retries: int = 2,
    heartbeat_callback: HeartbeatCallback | None = None,
) -> ConsumerExplainer | None:
    """Generate a plain-English consumer explainer for ONE document.

    Builds the finalized Prompt 2 from the document's gated extraction (and the
    analysis when present), calls the FREE-FIRST cascade with JSON response
    format, parses defensively with retries, and runs the server-side validator
    (quote de-citation + grade clamp) before returning.

    Returns None when there is no extraction to ground the explainer in, or when
    every attempt fails to parse — the caller decides how to surface that.
    """
    token = cancellation_token or CancellationToken()

    extraction = document.extraction
    if extraction is None:
        logger.warning(
            "generate_consumer_explainer: document %s has no extraction; skipping "
            "(explainer must be grounded in extracted evidence).",
            document.id,
        )
        return None

    user_prompt = (
        CONSUMER_EXPLAINER_USER_TEMPLATE.replace("{doc_type}", str(document.doc_type))
        .replace("{doc_title}", document.title or "Not specified")
        .replace("{regions}", ", ".join(document.regions) if document.regions else "Not specified")
        .replace("{extraction_json}", extraction.model_dump_json())
    )

    usage_tracker = UsageTracker()
    tracker_callback = usage_tracker.create_tracker("generate_consumer_explainer")

    last_exception: Exception | None = None

    for attempt in range(max_retries):
        await token.check_cancellation()
        await _maybe_await(heartbeat_callback() if heartbeat_callback else None)
        try:
            async with usage_tracking(tracker_callback):
                response = await acompletion_with_fallback(
                    messages=[
                        {"role": "system", "content": CONSUMER_EXPLAINER_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    model_priority=_OVERVIEW_PRIORITY,
                    response_format={"type": "json_object"},
                    temperature=0,
                    heartbeat_callback=heartbeat_callback,
                )
            logger.info("generate_consumer_explainer %s used model %s", document.id, response.model)

            content = _extract_json_from_response(response)
            parsed_dict = json.loads(_strip_json_fences(content))
            if not isinstance(parsed_dict, dict):
                raise ValueError("Consumer explainer response was not a JSON object")

            explainer = ConsumerExplainer.model_validate(parsed_dict, strict=False)
            explainer = _validate_consumer_explainer(explainer, extraction, document)

            summary, records = usage_tracker.consume_summary()
            log_usage_summary(
                summary,
                records,
                context=f"document_{document.id}",
                reason="success",
                operation_type="consumer_explainer",
                product_id=document.product_id,
                document_id=document.id,
                document_url=document.url,
            )
            return explainer
        except asyncio.CancelledError:
            raise
        except Exception as exception:  # noqa: BLE001 - retry on any parse/LLM failure
            last_exception = exception
            logger.warning(
                "generate_consumer_explainer attempt %d/%d failed for document %s: %s",
                attempt + 1,
                max_retries,
                document.id,
                exception,
            )

    logger.error(
        "Failed to generate consumer explainer for document %s after %d attempts: %s",
        document.id,
        max_retries,
        last_exception,
    )
    return None


async def generate_product_consumer_explainer(
    db: AgnosticDatabase,
    product_slug: str,
    product_svc: ProductService,
    document_svc: DocumentService,
    *,
    cancellation_token: CancellationToken | None = None,
    max_retries: int = 2,
    heartbeat_callback: HeartbeatCallback | None = None,
) -> ConsumerExplainer | None:
    """Synthesize ONE product-level consumer explainer (roll-up) across all core docs.

    This is the consumer-facing, product-page output: it reads every core document's
    extraction (and analysis when present), runs the roll-up prompt on the FREE-FIRST
    cascade, and validates citations against the UNION of all the documents' evidence
    quotes (a quote may legitimately come from any of the product's documents).
    Returns None when no core document has extraction, or when every attempt fails.
    """
    token = cancellation_token or CancellationToken()

    product = await product_svc.get_product_by_slug(db, product_slug)
    product_name = product.name if product else product_slug

    documents = await document_svc.get_product_documents_by_slug(db, product_slug)
    core_docs = [
        doc
        for doc in documents
        if doc.doc_type in OVERVIEW_CORE_DOC_TYPES and doc.extraction is not None
    ]
    if not core_docs:
        logger.warning(
            "generate_product_consumer_explainer: no core document with extraction for %s",
            product_slug,
        )
        return None

    allowed_citations: list[SourceCitation] = []
    doc_inputs: list[dict[str, Any]] = []
    regions: set[str] = set()
    for doc in core_docs:
        extraction = doc.extraction
        if extraction is None:
            continue
        allowed_citations.extend(_collect_extraction_citations(extraction, doc))
        regions.update(doc.regions or [])
        doc_inputs.append(
            {
                "title": doc.title or doc.doc_type,
                "doc_type": doc.doc_type,
                "regions": doc.regions or [],
                "extraction": extraction.model_dump(),
                "analysis": doc.analysis.model_dump() if doc.analysis else None,
            }
        )

    user_prompt = (
        CONSUMER_EXPLAINER_ROLLUP_USER_TEMPLATE.replace("{product_name}", product_name)
        .replace("{regions}", ", ".join(sorted(regions)) if regions else "Not specified")
        .replace("{extraction_json}", json.dumps(doc_inputs, default=str))
    )

    usage_tracker = UsageTracker()
    tracker_callback = usage_tracker.create_tracker("generate_product_consumer_explainer")
    last_exception: Exception | None = None

    for attempt in range(max_retries):
        await token.check_cancellation()
        await _maybe_await(heartbeat_callback() if heartbeat_callback else None)
        try:
            async with usage_tracking(tracker_callback):
                response = await acompletion_with_fallback(
                    messages=[
                        {"role": "system", "content": CONSUMER_EXPLAINER_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    model_priority=_OVERVIEW_PRIORITY,
                    response_format={"type": "json_object"},
                    temperature=0,
                    heartbeat_callback=heartbeat_callback,
                )
            logger.info(
                "generate_product_consumer_explainer %s used model %s", product_slug, response.model
            )
            content = _extract_json_from_response(response)
            parsed_dict = json.loads(_strip_json_fences(content))
            if not isinstance(parsed_dict, dict):
                raise ValueError("Product consumer explainer response was not a JSON object")
            explainer = ConsumerExplainer.model_validate(parsed_dict, strict=False)
            explainer.is_product_rollup = True
            explainer = _validate_consumer_explainer_quotes(explainer, allowed_citations)

            summary, records = usage_tracker.consume_summary()
            log_usage_summary(
                summary,
                records,
                context=f"product_{product_slug}",
                reason="success",
                operation_type="consumer_explainer",
                product_id=product.id if product else None,
            )
            return explainer
        except asyncio.CancelledError:
            raise
        except Exception as exception:  # noqa: BLE001 - retry on any parse/LLM failure
            last_exception = exception
            logger.warning(
                "generate_product_consumer_explainer attempt %d/%d failed for %s: %s",
                attempt + 1,
                max_retries,
                product_slug,
                exception,
            )

    logger.error(
        "Failed to generate product consumer explainer for %s after %d attempts: %s",
        product_slug,
        max_retries,
        last_exception,
    )
    return None


def _normalize_compliance_regime_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Coerce LLM compliance regime fields before model validation."""
    normalized = dict(payload)
    rationale = normalized.pop("rationale", None)
    if rationale is not None and not normalized.get("assessment_notes"):
        normalized["assessment_notes"] = rationale
    for key in ("strengths", "gaps"):
        value = normalized.get(key)
        if isinstance(value, str):
            normalized[key] = [value] if value.strip() else []
    return normalized


async def generate_product_compliance(
    db: AgnosticDatabase,
    product_slug: str,
    product_svc: ProductService,
    document_svc: DocumentService,
    *,
    cancellation_token: CancellationToken | None = None,
    max_retries: int = 2,
) -> dict[str, ComplianceBreakdown] | None:
    """Generate a JUSTIFIED product-level compliance assessment across all core docs.

    Produces, per applicable regime, a ComplianceBreakdown (score + status + concrete
    strengths and gaps) grounded in the documents — the "why" behind each compliance
    grade. Only regimes the documents give a basis to assess are returned. Returns
    None when there is no core extraction or every attempt fails.
    """
    token = cancellation_token or CancellationToken()

    product = await product_svc.get_product_by_slug(db, product_slug)
    product_name = product.name if product else product_slug

    documents = await document_svc.get_product_documents_by_slug(db, product_slug)
    core_docs = [
        doc
        for doc in documents
        if doc.doc_type in OVERVIEW_CORE_DOC_TYPES and doc.extraction is not None
    ]
    if not core_docs:
        logger.warning(
            "generate_product_compliance: no core document with extraction for %s", product_slug
        )
        return None

    doc_inputs: list[dict[str, Any]] = []
    regions: set[str] = set()
    for doc in core_docs:
        extraction = doc.extraction
        if extraction is None:
            continue
        regions.update(doc.regions or [])
        doc_inputs.append(
            {
                "title": doc.title or doc.doc_type,
                "doc_type": doc.doc_type,
                "regions": doc.regions or [],
                "extraction": extraction.model_dump(),
                "analysis": doc.analysis.model_dump() if doc.analysis else None,
            }
        )

    user_prompt = (
        COMPLIANCE_ASSESSMENT_USER_TEMPLATE.replace("{product_name}", product_name)
        .replace("{regions}", ", ".join(sorted(regions)) if regions else "Not specified")
        .replace("{docs_json}", json.dumps(doc_inputs, default=str))
    )

    usage_tracker = UsageTracker()
    tracker_callback = usage_tracker.create_tracker("generate_product_compliance")
    last_exception: Exception | None = None

    for attempt in range(max_retries):
        await token.check_cancellation()
        try:
            async with usage_tracking(tracker_callback):
                response = await acompletion_with_fallback(
                    messages=[
                        {"role": "system", "content": COMPLIANCE_ASSESSMENT_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    model_priority=_OVERVIEW_PRIORITY,
                    response_format={"type": "json_object"},
                    temperature=0,
                )
            logger.info(
                "generate_product_compliance %s used model %s", product_slug, response.model
            )
            content = _extract_json_from_response(response)
            parsed = json.loads(_strip_json_fences(content))
            if not isinstance(parsed, dict):
                raise ValueError("Compliance assessment response was not a JSON object")

            breakdowns: dict[str, ComplianceBreakdown] = {}
            for regime, payload in parsed.items():
                if not isinstance(payload, dict):
                    continue
                try:
                    breakdowns[str(regime)] = ComplianceBreakdown.model_validate(
                        _normalize_compliance_regime_payload(payload), strict=False
                    )
                except Exception as item_error:  # noqa: BLE001 - skip one bad regime, keep the rest
                    logger.debug(
                        "generate_product_compliance: dropped invalid regime %s for %s: %s",
                        regime,
                        product_slug,
                        item_error,
                    )
            if not breakdowns:
                raise ValueError("No valid compliance regimes parsed")

            summary, records = usage_tracker.consume_summary()
            log_usage_summary(
                summary,
                records,
                context=f"product_{product_slug}",
                reason="success",
                operation_type="compliance_assessment",
                product_id=product.id if product else None,
            )
            return breakdowns
        except asyncio.CancelledError:
            raise
        except Exception as exception:  # noqa: BLE001 - retry on any parse/LLM failure
            last_exception = exception
            logger.warning(
                "generate_product_compliance attempt %d/%d failed for %s: %s",
                attempt + 1,
                max_retries,
                product_slug,
                exception,
            )

    logger.error(
        "Failed to generate product compliance for %s after %d attempts: %s",
        product_slug,
        max_retries,
        last_exception,
    )
    return None


async def generate_product_overview(
    db: AgnosticDatabase,
    product_slug: str,
    force_regenerate: bool = False,
    product_svc: ProductService | None = None,
    document_svc: DocumentService | None = None,
    cancellation_token: CancellationToken | None = None,
    on_progress: HeartbeatCallback | None = None,
    job_id: str | None = None,
) -> MetaSummary:
    """
    Generate a cached product overview from analyzed core policy documents.

    Called by the crawl pipeline after `analyse_product_documents`. The result is stored on
    the product record and returned by the HTTP API for the public/dashboard product page
    (`GET .../products/{slug}/overview`). This path uses structured per-document
    extraction + analysis as context — not Pinecone embedding search.

    Cache behaviour:
    - If a cached overview exists and force_regenerate is False, return it.
    - When any document changes, the DocumentService deletes the cached overview.

    Args:
        product_slug: The product slug to generate meta-summary for
        force_regenerate: If True, bypass cache and regenerate meta-summary
        product_svc: Optional ProductService instance (for dependency injection)
        document_svc: Optional DocumentService instance (for dependency injection)
        cancellation_token: Optional cancellation token for interrupting the operation
        on_progress: Optional liveness ping fired before each long sub-step (aggregation
            rebuild, LLM synthesis) so a caller can keep the job heartbeat fresh. A None
            callback is a no-op, leaving behaviour outside the pipeline unchanged.

    Returns:
        MetaSummary: The generated overview payload

    Raises:
        asyncio.CancelledError: If cancellation is requested
    """
    # For HTTP requests, create a fresh token if none provided
    # The global token is for signal-based cancellation (Ctrl+C) and may be in a cancelled state
    if cancellation_token is None:
        token = CancellationToken()
    else:
        token = cancellation_token
    if not product_svc or not document_svc:
        raise ValueError("product_svc and document_svc are required")

    documents = await document_svc.get_product_documents_by_slug(db, product_slug)
    logger.info(f"Generating product overview for {product_slug} with {len(documents)} documents")

    product = await product_svc.get_product_by_slug(db, product_slug)
    if not product:
        raise ValueError(f"Product not found for slug {product_slug}")

    # Check cache unless force_regenerate is True
    if not force_regenerate:
        cached_overview_data = await product_svc.get_product_overview_data(db, product_slug)
        if cached_overview_data and cached_overview_data.get("overview"):
            cached = cached_overview_data["overview"]
            logger.info(f"Using cached product overview for {product_slug}")
            try:
                return MetaSummary.model_validate(cached)
            except Exception as e:
                logger.warning(
                    f"Failed to parse cached product overview for {product_slug}: {e}. Regenerating..."
                )

    # Cache miss or invalid — generate new product overview.
    logger.info(f"Generating new product overview for {product_slug}")

    await token.check_cancellation()
    if on_progress is not None:
        await _maybe_await(on_progress())
    rollup_service = ProductRollupService(DocumentRepository())
    hydrated_rollup = await rollup_service.build_product_rollup(
        db, product_id=product.id, product_slug=product_slug
    )
    document_summaries = [DocumentSummary.from_document(doc) for doc in documents]
    topic_report = build_product_topic_report(
        product_slug=product_slug,
        rollup=hydrated_rollup,
        documents=document_summaries,
    )

    # Filter to core documents only for the synthesis.
    # Non-core docs (community_guidelines, copyright_policy, etc.) are analysed
    # per-document but excluded from the product overview — they address editorial/IP
    # rules rather than data/privacy risk and would dilute the signal.
    core_docs = [doc for doc in documents if doc.doc_type in OVERVIEW_CORE_DOC_TYPES]
    excluded_types = {doc.doc_type for doc in documents} - OVERVIEW_CORE_DOC_TYPES
    if excluded_types:
        logger.info(
            f"Excluding {len(excluded_types)} non-core doc type(s) from overview: {excluded_types}"
        )

    if not core_docs:
        # No core documents at all — fall back to all documents
        logger.warning(
            f"No core documents found for {product_slug}. Using all {len(documents)} documents."
        )
        core_docs = documents

    # Build rich per-document input: extraction + analysis for each core doc.
    # This gives the model concrete evidence rather than just aggregated findings.
    doc_inputs: list[dict[str, Any]] = []
    for doc in core_docs:
        if not doc.analysis:
            logger.debug(f"Skipping document {doc.id} ({doc.doc_type}) — not yet analysed")
            continue
        entry: dict[str, Any] = {
            "document_type": doc.doc_type,
            "title": doc.title or doc.doc_type,
            "url": doc.url,
            "locale": doc.locale,
            "regions": [r.value if hasattr(r, "value") else r for r in (doc.regions or [])],
            "analysis": {
                "summary": doc.analysis.summary,
                "scores": {
                    k: {"score": v.score, "justification": v.justification}
                    for k, v in doc.analysis.scores.items()
                },
                "risk_score": doc.analysis.risk_score,
                "keypoints": doc.analysis.keypoints or [],
                "applicability": doc.analysis.applicability,
                "coverage_gaps": doc.analysis.coverage_gaps or [],
                "critical_clauses": [
                    {
                        "clause_type": c.clause_type,
                        "section_title": c.section_title,
                        "quote": c.quote,
                        "risk_level": c.risk_level,
                        "plain_english": c.plain_english or c.analysis,
                        "why_notable": c.why_notable,
                        "compliance_impact": c.compliance_impact,
                    }
                    for c in (doc.analysis.critical_clauses or [])
                ],
            },
        }
        if doc.extraction:
            entry["extraction"] = {
                "data_collected": [
                    {"data_type": d.data_type, "sensitivity": d.sensitivity}
                    for d in doc.extraction.data_collected
                ],
                "data_purposes": [
                    {"data_type": data_purpose.data_type, "purposes": data_purpose.purposes}
                    for data_purpose in doc.extraction.data_purposes
                ],
                "third_party_details": [
                    {
                        "recipient": t.recipient,
                        "data_shared": t.data_shared,
                        "purpose": t.purpose,
                        "risk_level": t.risk_level,
                    }
                    for t in doc.extraction.third_party_details
                ],
                "user_rights": [
                    {"right_type": r.right_type, "mechanism": r.mechanism}
                    for r in doc.extraction.user_rights
                ],
                "ai_usage": [
                    {
                        "usage_type": a.usage_type,
                        "description": a.description,
                        "opt_out_available": a.opt_out_available,
                    }
                    for a in doc.extraction.ai_usage
                ],
                "privacy_signals": doc.extraction.privacy_signals.model_dump()
                if doc.extraction.privacy_signals
                else None,
                "dangers": [d.value for d in doc.extraction.dangers],
                "benefits": [b.value for b in doc.extraction.benefits],
            }
        doc_inputs.append(entry)

    # Refuse to synthesise an overview when no document was successfully analysed.
    # With no analysed input the model fabricates a confident but false verdict
    # (e.g. "no documents supplied", risk_score 0, verdict very_pervasive) that reads
    # like a real assessment. Raise instead so the pipeline marks the job failed rather
    # than publishing a misleading overview.
    if not doc_inputs:
        raise ValueError(
            f"Cannot generate overview for {product_slug}: none of {len(core_docs)} "
            "core document(s) have analysis (upstream document analysis failed)."
        )

    # Include cross-document conflicts from the aggregation engine.
    # These are deterministically detected facts (e.g., one doc says data is not sold,
    # another says it can be shared with commercial partners) that the LLM should weigh.
    conflicts_section = ""
    if hydrated_rollup.conflicts:
        conflicts_section = (
            "\nCross-document conflicts detected by the analysis engine "
            "(report these in the contradictions field):\n"
            + json.dumps([c.model_dump() for c in hydrated_rollup.conflicts], indent=2)
            + "\n"
        )

    topic_signals = [
        {
            "topic": topic.topic,
            "status": topic.status,
            "stance": topic.stance,
            "topic_score": topic.topic_score,
            "rationale": topic.rationale,
            "sample_findings": [finding.value for finding in topic.findings[:3]],
        }
        for topic in topic_report.topics
    ]

    prompt = f"""Product: {product_slug}
Core documents analyzed: {len(doc_inputs)} of {len(core_docs)} core documents
Document types: {", ".join(doc.doc_type for doc in core_docs if doc.analysis)}
Deterministic per-topic signals:
{json.dumps(topic_signals, indent=2)}
{conflicts_section}
Per-document analyses and extractions:
{json.dumps(doc_inputs, indent=2)}
"""

    # Set up usage tracking for meta-summary generation
    usage_tracker = UsageTracker()
    tracker_callback = usage_tracker.create_tracker("generate_overview")

    # Check for cancellation before making LLM call
    await token.check_cancellation()
    if on_progress is not None:
        await _maybe_await(on_progress())

    from src.analyzers.llm_review import llm_review_overview
    from src.analyzers.overview_guards import (
        MAX_OVERVIEW_RE_ROLLS,
        OverviewValidationResult,
        _collect_citations,
        format_overview_retry_feedback,
        merge_llm_review,
        validate_overview,
    )
    from src.services.thin_evidence_gate import check_thin_evidence
    from src.services.topic_evidence_fallback import attach_fallback_evidence

    is_thin, thin_reason = check_thin_evidence(
        [d.doc_type for d in core_docs if d.doc_type in OVERVIEW_CORE_DOC_TYPES]
    )
    if is_thin:
        logger.warning(
            "Thin evidence for %s: %s — overview may be incomplete",
            product_slug,
            thin_reason,
        )

    try:
        async with usage_tracking(tracker_callback):
            feedback_suffix = ""
            meta_summary: MetaSummary | None = None
            validation: OverviewValidationResult | None = None

            for attempt in range(1, MAX_OVERVIEW_RE_ROLLS + 1):
                if attempt > 1:
                    logger.info(
                        "Regenerating overview for %s after validation feedback (attempt %d/%d)",
                        product_slug,
                        attempt,
                        MAX_OVERVIEW_RE_ROLLS,
                    )
                    await token.check_cancellation()
                    if on_progress is not None:
                        await _maybe_await(on_progress())

                user_content = prompt + feedback_suffix

                # Wrap the LLM call in a cancellable task
                llm_task = asyncio.create_task(
                    acompletion_with_fallback(
                        messages=[
                            {
                                "role": "system",
                                "content": PRODUCT_OVERVIEW_PROMPT,
                            },
                            {"role": "user", "content": user_content},
                        ],
                        model_priority=_OVERVIEW_PRIORITY,
                        response_format={"type": "json_object"},
                        temperature=0,
                        heartbeat_callback=on_progress,
                    )
                )

                # Wait for either completion or cancellation
                cancellation_task = asyncio.create_task(token.cancelled.wait())
                done, pending = await asyncio.wait(
                    [llm_task, cancellation_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # Cancel pending tasks
                for pending_task in pending:
                    pending_task.cancel()
                    try:
                        await pending_task
                    except asyncio.CancelledError:
                        pass

                # If cancellation was requested, cancel the LLM task
                if token.is_cancelled():
                    llm_task.cancel()
                    try:
                        await llm_task
                    except asyncio.CancelledError:
                        pass
                    raise asyncio.CancelledError("Meta-summary generation cancelled")

                # Get the response
                response = await llm_task

                choice = response.choices[0]
                # Non-streaming responses always have message attribute
                if not hasattr(choice, "message"):
                    raise ValueError("Unexpected response format: missing message attribute")
                message = choice.message  # type: ignore[attr-defined]
                if not message:
                    raise ValueError("Unexpected response format: message is None")
                content = message.content  # type: ignore[attr-defined]
                if not content:
                    raise ValueError("Empty response from LLM")

                logger.debug(content)

                # Parse the product overview
                overview_dict = json.loads(content)
                _merge_legacy_dimension_justifications(overview_dict)

                # Parse contradictions before model validation
                raw_contradictions = overview_dict.pop("contradictions", None)

                meta_summary = MetaSummary.model_validate(overview_dict, strict=False)
                meta_summary.coverage = hydrated_rollup.coverage
                if meta_summary.dangers:
                    meta_summary.dangers = await filter_danger_strings_llm(meta_summary.dangers)

                # Attach contradictions
                if isinstance(raw_contradictions, list):
                    try:
                        meta_summary.contradictions = [
                            ProductContradiction.model_validate(c)
                            for c in raw_contradictions
                            if isinstance(c, dict)
                        ]
                    except Exception as e:
                        logger.warning(f"Failed to parse contradictions: {e}")

                # Attach deterministic topic stances used for both UI explainability and scoring.
                meta_summary.topic_stances = []
                for topic in topic_report.topics:
                    cited_document_ids: set[str] = set()
                    evidence_count = 0
                    for finding in topic.findings:
                        cited_document_ids.update(finding.document_ids)
                        evidence_count += len(finding.citations)
                    for conflict in topic.conflicts:
                        cited_document_ids.update(conflict.document_ids)
                        evidence_count += len(conflict.citations)
                    primary_finding = _headline_finding_for_topic(topic)
                    primary_conflict = topic.conflicts[0] if topic.conflicts else None
                    supporting_citations = _topic_supporting_citations(topic)
                    if primary_finding and primary_finding.value:
                        headline_claim = _truncate_text(primary_finding.value)
                    elif primary_conflict and primary_conflict.description:
                        headline_claim = _truncate_text(primary_conflict.description)
                    elif topic.status in {"missing", "not_disclosed"}:
                        headline_claim = "No verifiable disclosure found across analyzed documents."
                    else:
                        headline_claim = None

                    meta_summary.topic_stances.append(
                        TopicStanceBreakdown(
                            topic=topic.topic,
                            status=topic.status,
                            stance=topic.stance,
                            topic_score=topic.topic_score,
                            rationale=topic.rationale,
                            rationale_key=topic.rationale_key,
                            rationale_params=topic.rationale_params,
                            evidence_count=evidence_count,
                            document_count=len(cited_document_ids),
                            headline_claim=headline_claim,
                            supporting_citations=supporting_citations,
                            conflict_note=_truncate_text(
                                primary_conflict.description if primary_conflict else None
                            ),
                            why_it_matters=_topic_why_it_matters(
                                topic=str(topic.topic),
                                status=str(topic.status),
                                stance=str(topic.stance),
                                conflict_count=len(topic.conflicts),
                            ),
                            recommended_action=_topic_recommended_action(
                                topic=str(topic.topic),
                                status=str(topic.status),
                                stance=str(topic.stance),
                            ),
                        )
                    )

                topic_rows: dict[InsightCategory, dict[str, Any]] = {
                    topic.topic: {
                        "status": topic.status,
                        "topic_score": topic.topic_score,
                    }
                    for topic in topic_report.topics
                }
                topic_blended = compose_product_risk_from_topics(topic_rows)
                legacy_blended = _weighted_product_risk_score(core_docs)
                dimension_risk = _calculate_overview_risk_score(meta_summary.scores)
                if legacy_blended is not None:
                    logger.info(
                        "overview scoring comparison for %s: legacy_doc=%s topic=%s dimension=%s",
                        product_slug,
                        legacy_blended,
                        topic_blended,
                        dimension_risk,
                    )
                else:
                    logger.info(
                        "overview scoring comparison for %s: topic=%s dimension=%s",
                        product_slug,
                        topic_blended,
                        dimension_risk,
                    )

                _reconcile_meta_summary_risk(meta_summary)

                if meta_summary.topic_stances:
                    attached = await attach_fallback_evidence(meta_summary.topic_stances, core_docs)
                    if attached:
                        logger.info("Attached %d fallback citations to %s", attached, product_slug)

                overview_dict = meta_summary.model_dump(mode="json")
                deterministic = validate_overview(overview_dict, has_adequate_evidence=not is_thin)

                citations_for_review = _collect_citations(overview_dict.get("topic_stances") or [])
                llm_result = await llm_review_overview(overview_dict, citations_for_review)
                validation = merge_llm_review(deterministic, llm_result)

                if validation.should_re_roll:
                    reasons = "; ".join(validation.re_roll_reasons)
                    logger.warning(
                        "Overview validation failed for %s (attempt %d/%d): %s",
                        product_slug,
                        attempt,
                        MAX_OVERVIEW_RE_ROLLS,
                        reasons,
                    )
                    if attempt >= MAX_OVERVIEW_RE_ROLLS:
                        raise ValueError(
                            f"Overview validation failed for {product_slug}: {reasons}"
                        )
                    feedback_suffix = format_overview_retry_feedback(validation.re_roll_reasons)
                    continue

                break

            if meta_summary is None or validation is None:
                raise ValueError(f"Overview generation produced no result for {product_slug}")

            for warning in validation.warnings:
                logger.info("Overview warning for %s: %s", product_slug, warning)

        # Save to database (simple single-cache entry)
        await product_svc.save_product_overview(
            db,
            product_slug=product_slug,
            meta_summary=meta_summary,
            job_id=job_id,
            product_id=product.id,
        )
        logger.info(f"✓ Saved product overview for {product_slug}")

        # Log LLM usage for meta-summary generation (success case)
        usage_summary, records = usage_tracker.consume_summary()
        log_usage_summary(
            usage_summary,
            records,
            context=f"product_{product_slug}",
            reason="success",
            operation_type="product_overview",
            product_slug=product_slug,
        )

        return meta_summary
    except asyncio.CancelledError:
        logger.info(f"Product overview generation cancelled for {product_slug}")
        raise
    except Exception as e:
        # Log LLM usage even on failure
        usage_summary, records = usage_tracker.consume_summary()
        log_usage_summary(
            usage_summary,
            records,
            context=f"product_{product_slug}",
            reason="failed",
            operation_type="product_overview",
            product_slug=product_slug,
        )

        # Log the full error with context
        logger.error(
            f"Error generating product overview for {product_slug}: {str(e)}",
            exc_info=True,
        )

        # Re-raise the exception so callers can handle it appropriately
        # This provides transparency about what actually failed
        raise RuntimeError(
            f"Failed to generate product overview for {product_slug}: {str(e)}"
        ) from e


def _document_to_deep_analysis(document: Document) -> DocumentDeepAnalysis | None:
    """Build a DocumentDeepAnalysis from a document whose analysis already includes deep fields.

    Since analyse_document() now always runs the deep analysis step, this is a
    pure data-mapping function — no additional LLM calls required.
    """
    if not document.analysis:
        return None

    last_updated = _extract_last_updated_from_metadata(document.metadata)

    return DocumentDeepAnalysis(
        document_id=document.id,
        document_type=document.doc_type,
        title=document.title,
        url=document.url,
        effective_date=document.effective_date,
        last_updated=last_updated,
        locale=document.locale,
        regions=document.regions,
        analysis=document.analysis,
        critical_clauses=document.analysis.critical_clauses or [],
        document_risk_breakdown=document.analysis.document_risk_breakdown
        or DocumentRiskBreakdown(overall_risk=document.analysis.risk_score),
        key_sections=document.analysis.key_sections or [],
    )


async def generate_document_deep_analysis(
    db: AgnosticDatabase,
    document: Document,
    document_svc: DocumentService,
) -> DocumentDeepAnalysis:
    """Return deep analysis for a single document.

    If the document has not been analysed yet, run analysis first (which always
    includes the clause-level deep analysis step).
    """
    if not document.analysis:
        analysis = await analyse_document(document)
        if analysis:
            document.analysis = analysis
            await document_svc.update_document(db, document, invalidate_product_overview=True)

    result = _document_to_deep_analysis(document)
    if not result:
        raise ValueError(f"Failed to generate analysis for document {document.id}")
    return result


async def generate_product_deep_analysis(
    db: AgnosticDatabase,
    product_slug: str,
    force_regenerate: bool = False,
    product_svc: ProductService | None = None,
    document_svc: DocumentService | None = None,
) -> ProductDeepAnalysis:
    """
    Generate deep analysis (Level 3) for a product.

    Uses an iterative approach:
    1. Generate deep analysis for each document individually
    2. Aggregate results for cross-document analysis and compliance
    """
    if not product_svc or not document_svc:
        raise ValueError("product_svc and document_svc are required")
    product_svc = product_svc
    document_svc = document_svc

    # First ensure we have Level 2 analysis
    analysis = await product_svc.get_product_analysis(db, product_slug)
    if not analysis:
        # Generate meta-summary first (which creates Level 2)
        logger.info(f"Level 2 analysis not found for {product_slug}, generating...")
        await generate_product_overview(
            db, product_slug=product_slug, product_svc=product_svc, document_svc=document_svc
        )
        analysis = await product_svc.get_product_analysis(db, product_slug)
        if not analysis:
            raise ValueError(f"Failed to generate Level 2 analysis for {product_slug}")

    # Get all documents with full text
    documents = await document_svc.get_product_documents_by_slug(db, product_slug)
    if not documents:
        raise ValueError(f"No documents found for {product_slug}")

    # Skip excluded doc types — same set as _weighted_product_risk_score.
    documents = [d for d in documents if d.doc_type not in _PRODUCT_OVERVIEW_EXCLUDED_DOC_TYPES]

    logger.info(f"Generating deep analysis for {product_slug} with {len(documents)} documents")

    # Compute document signature for caching
    current_signature = _compute_document_signature(documents)

    # Check cache unless force_regenerate
    if not force_regenerate:
        cached_deep_analysis = await product_svc.get_deep_analysis(db, product_slug)
        if cached_deep_analysis:
            cached_signature = cached_deep_analysis.get("document_signature")
            cached_data = cached_deep_analysis.get("deep_analysis")

            if cached_signature == current_signature and cached_data:
                logger.info(
                    f"Using cached deep analysis for {product_slug} "
                    f"(signature match: {current_signature[:16]}...)"
                )
                try:
                    deep_analysis: ProductDeepAnalysis = ProductDeepAnalysis.model_validate(
                        cached_data
                    )
                    return deep_analysis
                except Exception as e:
                    logger.warning(
                        f"Failed to parse cached deep analysis for {product_slug}: {e}. "
                        "Regenerating..."
                    )

    # Cache miss or invalid - generate new deep analysis
    logger.info(f"Generating new deep analysis for {product_slug}")

    usage_tracker = UsageTracker()

    # Phase 1: Build DocumentDeepAnalysis from each document's already-enriched analysis.
    # analyse_document() always runs the clause-level deep analysis step, so no additional
    # LLM calls are needed here.
    document_analyses: list[DocumentDeepAnalysis] = []

    for doc in documents:
        doc_analysis = _document_to_deep_analysis(doc)
        if doc_analysis:
            document_analyses.append(doc_analysis)
        else:
            logger.warning(
                f"Document {doc.id} ({doc.title or doc.doc_type}) has no analysis — "
                "run analyse_product_documents() first"
            )

    if not document_analyses:
        raise ValueError(
            f"Failed to generate deep analysis for any documents for {product_slug}. "
            "This may occur if documents are missing analysis (Level 2) or text content."
        )

    # Phase 2: Aggregate Analysis
    logger.info("Generating aggregate deep analysis...")

    # Build rich per-document input identical to the overview pipeline.
    # This gives the model concrete, structured evidence rather than a lossy text digest.
    doc_inputs: list[dict[str, Any]] = []
    for doc in documents:
        if not doc.analysis:
            continue
        entry: dict[str, Any] = {
            "document_type": doc.doc_type,
            "title": doc.title or doc.doc_type,
            "url": doc.url,
            "locale": doc.locale,
            "regions": [r.value if hasattr(r, "value") else r for r in (doc.regions or [])],
            "effective_date": doc.effective_date.isoformat() if doc.effective_date else None,
            "analysis": {
                "summary": doc.analysis.summary,
                "scores": {
                    k: {"score": v.score, "justification": v.justification}
                    for k, v in doc.analysis.scores.items()
                },
                "risk_score": doc.analysis.risk_score,
                "verdict": doc.analysis.verdict,
                "keypoints": doc.analysis.keypoints or [],
                "applicability": doc.analysis.applicability,
                "coverage_gaps": doc.analysis.coverage_gaps or [],
                "critical_clauses": [
                    {
                        "clause_type": c.clause_type,
                        "section_title": c.section_title,
                        "quote": c.quote,
                        "risk_level": c.risk_level,
                        "plain_english": c.plain_english or c.analysis,
                        "why_notable": c.why_notable,
                        "compliance_impact": c.compliance_impact,
                    }
                    for c in (doc.analysis.critical_clauses or [])[:10]
                ],
            },
        }
        if doc.extraction:
            entry["extraction"] = {
                "data_collected": [
                    {"data_type": d.data_type, "sensitivity": d.sensitivity}
                    for d in doc.extraction.data_collected[:20]
                ],
                "data_purposes": [
                    {"data_type": data_purpose.data_type, "purposes": data_purpose.purposes}
                    for data_purpose in doc.extraction.data_purposes[:20]
                ],
                "third_party_details": [
                    {
                        "recipient": t.recipient,
                        "data_shared": t.data_shared,
                        "purpose": t.purpose,
                        "risk_level": t.risk_level,
                    }
                    for t in doc.extraction.third_party_details[:15]
                ],
                "user_rights": [
                    {"right_type": r.right_type, "mechanism": r.mechanism}
                    for r in doc.extraction.user_rights
                ],
                "ai_usage": [
                    {
                        "usage_type": a.usage_type,
                        "description": a.description,
                        "opt_out_available": a.opt_out_available,
                    }
                    for a in doc.extraction.ai_usage
                ],
                "privacy_signals": doc.extraction.privacy_signals.model_dump()
                if doc.extraction.privacy_signals
                else None,
                "dangers": [d.value for d in doc.extraction.dangers],
                "benefits": [b.value for b in doc.extraction.benefits],
            }
        doc_inputs.append(entry)

    aggregate_prompt = f"""Product: {product_slug}
Core documents: {len(doc_inputs)} analyzed

**Document scope note:**
- Global/product-wide documents affect all users → prioritize risks higher
- Product-specific documents affect only specific product users → still important but lower scope

Per-document analyses and extractions:
{json.dumps(doc_inputs, indent=2)}
"""

    tracker_callback = usage_tracker.create_tracker("aggregate_deep_analysis")

    try:
        async with usage_tracking(tracker_callback):
            response = await acompletion_with_fallback(
                messages=[
                    {
                        "role": "system",
                        "content": PRODUCT_DEEP_ANALYSIS_PROMPT,
                    },
                    {"role": "user", "content": aggregate_prompt},
                ],
                model_priority=_OVERVIEW_PRIORITY,
                response_format={"type": "json_object"},
            )

        choice = response.choices[0]
        if not hasattr(choice, "message"):
            raise ValueError("Unexpected response format: missing message attribute")
        message = choice.message  # type: ignore[attr-defined]
        if not message:
            raise ValueError("Unexpected response format: message is None")
        content = message.content  # type: ignore[attr-defined]
        if not content:
            raise ValueError("Empty response from LLM")

        agg_data = json.loads(content)

        # ── Cross-document analysis ──────────────────────────────────────────
        cda_raw = agg_data.get("cross_document_analysis", {})
        cross_document_analysis = CrossDocumentAnalysis(
            contradictions=cda_raw.get("contradictions", []),
            information_gaps=cda_raw.get("information_gaps", []),
            document_relationships=cda_raw.get("document_relationships", []),
        )

        # ── Procurement decision ─────────────────────────────────────────────
        procurement_decision: ProcurementDecision | None = None
        if pd_raw := agg_data.get("procurement_decision"):
            try:
                procurement_decision = ProcurementDecision.model_validate(pd_raw)
            except Exception as e:
                logger.warning(f"Failed to parse procurement_decision: {e}")

        # ── Data processing profile ──────────────────────────────────────────
        data_processing_profile: DataProcessingProfile | None = None
        if dpp_raw := agg_data.get("data_processing_profile"):
            try:
                data_processing_profile = DataProcessingProfile.model_validate(dpp_raw)
            except Exception as e:
                logger.warning(f"Failed to parse data_processing_profile: {e}")

        # ── Article-level compliance ─────────────────────────────────────────
        article_compliance: dict[str, RegulationArticleBreakdown] = {}
        for reg, reg_data in agg_data.get("article_compliance", {}).items():
            try:
                if not isinstance(reg_data, dict):
                    continue
                article_compliance[reg] = RegulationArticleBreakdown.model_validate(reg_data)
            except Exception as e:
                logger.warning(f"Failed to parse article_compliance[{reg}]: {e}. Skipping.")

        # ── Risk register ────────────────────────────────────────────────────
        risk_register: list[RiskRegisterItem] = []
        for item in agg_data.get("risk_register", []):
            try:
                risk_register.append(RiskRegisterItem.model_validate(item))
            except Exception as e:
                logger.warning(f"Failed to parse risk_register item: {e}. Skipping.")

        # ── Contract clause review ───────────────────────────────────────────
        contract_clause_review: list[ContractClauseReview] = []
        for item in agg_data.get("contract_clause_review", []):
            try:
                contract_clause_review.append(ContractClauseReview.model_validate(item))
            except Exception as e:
                logger.warning(f"Failed to parse contract_clause_review item: {e}. Skipping.")

        # ── Workforce data assessment ────────────────────────────────────────
        workforce_data_assessment: WorkforceDataAssessment | None = None
        if wda_raw := agg_data.get("workforce_data_assessment"):
            try:
                workforce_data_assessment = WorkforceDataAssessment.model_validate(wda_raw)
            except Exception as e:
                logger.warning(f"Failed to parse workforce_data_assessment: {e}")

        # ── DPIA trigger ─────────────────────────────────────────────────────
        dpia_trigger: DPIATriggerAssessment | None = None
        if dpia_raw := agg_data.get("dpia_trigger"):
            try:
                dpia_trigger = DPIATriggerAssessment.model_validate(dpia_raw)
            except Exception as e:
                logger.warning(f"Failed to parse dpia_trigger: {e}")

        # ── Security posture ─────────────────────────────────────────────────
        security_posture: SecurityPosture | None = None
        if sp_raw := agg_data.get("security_posture"):
            try:
                security_posture = SecurityPosture.model_validate(sp_raw)
            except Exception as e:
                logger.warning(f"Failed to parse security_posture: {e}")

        # ── Remediation roadmap ──────────────────────────────────────────────
        remediation_roadmap: list[RemediationItem] = []
        for item in agg_data.get("remediation_roadmap", []):
            try:
                remediation_roadmap.append(RemediationItem.model_validate(item))
            except Exception as e:
                logger.warning(f"Failed to parse remediation_roadmap item: {e}. Skipping.")

        # ── Business impact ──────────────────────────────────────────────────
        biz_impact_data = agg_data.get("business_impact", {})
        try:
            business_impact = BusinessImpactAssessment(
                for_individuals=IndividualImpact.model_validate(
                    biz_impact_data.get("for_individuals", {})
                ),
                for_businesses=BusinessImpact.model_validate(
                    biz_impact_data.get("for_businesses", {})
                ),
            )
        except Exception as e:
            logger.warning(f"Failed to parse business impact data: {e}. Using defaults.")
            business_impact = BusinessImpactAssessment(
                for_individuals=IndividualImpact(
                    privacy_risk_level="medium",
                    data_exposure_summary="Unable to assess",
                    recommended_actions=[],
                ),
                for_businesses=BusinessImpact(
                    liability_exposure=5,
                    contract_risk_score=5,
                    vendor_risk_score=5,
                    financial_impact="Unable to assess",
                    reputational_risk="Unable to assess",
                    operational_risk="Unable to assess",
                    recommended_actions=[],
                ),
            )

        deep_analysis = ProductDeepAnalysis(
            analysis=analysis,
            document_analyses=document_analyses,
            cross_document_analysis=cross_document_analysis,
            procurement_decision=procurement_decision,
            data_processing_profile=data_processing_profile,
            article_compliance=article_compliance,
            risk_register=risk_register,
            contract_clause_review=contract_clause_review,
            workforce_data_assessment=workforce_data_assessment,
            dpia_trigger=dpia_trigger,
            security_posture=security_posture,
            remediation_roadmap=remediation_roadmap,
            business_impact=business_impact,
        )

        # Save the result to database
        await product_svc.save_deep_analysis(
            db,
            product_slug=product_slug,
            deep_analysis=deep_analysis,
            document_signature=current_signature,
        )
        logger.info(f"✓ Saved deep analysis for {product_slug}")

        # Log usage
        usage_summary, records = usage_tracker.consume_summary()
        log_usage_summary(
            usage_summary,
            records,
            context=f"product_{product_slug}",
            reason="success",
            operation_type="deep_analysis",
            product_slug=product_slug,
        )

        return deep_analysis

    except Exception as e:
        logger.error(f"Error generating aggregate deep analysis: {str(e)}")

        # Log usage
        usage_summary, records = usage_tracker.consume_summary()
        log_usage_summary(
            usage_summary,
            records,
            context=f"product_{product_slug}",
            reason="failed",
            operation_type="deep_analysis",
            product_slug=product_slug,
        )

        raise


async def main() -> None:
    from src.core.database import db_session
    from src.services.service_factory import create_services

    async with db_session() as db:
        product_svc, document_svc = create_services()

        await analyse_product_documents(db, "notion", document_svc)

        print("Generating product overview:")
        print("=" * 50)
        overview = await generate_product_overview(
            db, "notion", product_svc=product_svc, document_svc=document_svc
        )
        logger.info(overview)
        print("\n" + "=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
