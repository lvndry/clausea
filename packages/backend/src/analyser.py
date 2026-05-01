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
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, Literal

from dotenv import load_dotenv
from motor.core import AgnosticDatabase

from src.core.logging import get_logger
from src.llm import acompletion_with_fallback
from src.models.document import (
    BusinessImpact,
    BusinessImpactAssessment,
    ContractClauseReview,
    CrossDocumentAnalysis,
    DataProcessingProfile,
    DocType,
    Document,
    DocumentAnalysis,
    DocumentAnalysisScores,
    DocumentDeepAnalysis,
    DocumentRiskBreakdown,
    DPIATriggerAssessment,
    IndividualImpact,
    MetaSummary,
    ProcurementDecision,
    ProductContradiction,
    ProductDeepAnalysis,
    RegulationArticleBreakdown,
    RemediationItem,
    RiskRegisterItem,
    SecurityPosture,
    WorkforceDataAssessment,
)
from src.models.finding import Aggregation
from src.prompts.analysis_prompts import (
    DOCUMENT_ANALYSIS_PROMPT,
    OVERVIEW_CORE_DOC_TYPES,
    PRODUCT_DEEP_ANALYSIS_PROMPT,
    PRODUCT_OVERVIEW_PROMPT,
)
from src.repositories.aggregation_repository import AggregationRepository
from src.repositories.document_repository import DocumentRepository
from src.repositories.finding_repository import FindingRepository
from src.services.aggregation_service import AggregationService
from src.services.document_service import DocumentService
from src.services.extraction_service import extract_document_facts
from src.services.product_service import ProductService
from src.utils.cancellation import CancellationToken
from src.utils.llm_usage import UsageTracker, log_usage_summary, usage_tracking

load_dotenv()
logger = get_logger(__name__)

ProgressCallback = Callable[[int, int, Document], Awaitable[None] | None]


async def _maybe_await(result: Awaitable[None] | None) -> None:
    if asyncio.iscoroutine(result):
        await result


async def analyse_product_documents(
    db: AgnosticDatabase,
    product_slug: str,
    document_svc: DocumentService,
    cancellation_token: CancellationToken | None = None,
    progress_callback: ProgressCallback | None = None,
) -> list[Document]:
    """Analyse all documents for a product concurrently (up to 3 at once).

    Each document analysis itself runs 4 parallel extraction clusters, so capping at 3
    concurrent documents balances throughput against LLM rate limits.
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

    async def _analyse_one(index: int, doc: Document) -> None:
        await token.check_cancellation()
        async with sem:
            logger.info(f"Processing document {index}/{total_docs}: {doc.title}")
            if progress_callback:
                await _maybe_await(progress_callback(index, total_docs, doc))
            try:
                analysis = await analyse_document(doc, cancellation_token=token)
                if analysis:
                    doc.analysis = analysis
                    await document_svc.update_document(db, doc, invalidate_product_overview=False)
                    logger.info(f"✓ Stored analysis for document {doc.id}")
                else:
                    logger.warning(f"✗ Failed to generate analysis for document {doc.id}")
            except asyncio.CancelledError:
                logger.info(f"Summarization cancelled at document {index}/{total_docs}")
                raise

    await asyncio.gather(*[_analyse_one(i, doc) for i, doc in enumerate(documents, 1)])
    logger.info(f"✓ Successfully analysed all {total_docs} documents for {product_slug}")
    return documents


def _compute_document_hash(document: Document) -> str:
    """Compute a hash for the document content to enable caching."""
    content = f"{document.text}{document.doc_type}"
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


def _calculate_risk_score(scores: dict[str, DocumentAnalysisScores]) -> int:
    """
    Calculate overall risk score from component scores.

    Higher component scores = better for the user. Risk is the inverse of that
    weighted blend so minimal-data / low-sharing / strong-security policies
    score clearly lower than ad-heavy, broadly shared data practices.

    Weights (sum 1.0): data_collection_scope and third_party_sharing dominate;
    transparency, user_control, retention, and security add nuance (e.g. E2EE).
    """
    weights = {
        "transparency": 0.14,
        "data_collection_scope": 0.26,
        "user_control": 0.18,
        "third_party_sharing": 0.24,
        "data_retention_score": 0.10,
        "security_score": 0.08,
    }

    weighted_sum = 0.0
    total_weight = 0.0

    for score_name, weight in weights.items():
        if score_name in scores:
            score_value = scores[score_name].score
            weighted_sum += score_value * weight
            total_weight += weight

    if total_weight == 0:
        return 5  # Default middle score if no scores available

    # Calculate weighted average
    weighted_avg = weighted_sum / total_weight

    # Risk score: lower component scores = higher risk
    # So risk_score = 10 - weighted_average (inverted)
    risk_score = round(10 - weighted_avg)
    return max(0, min(10, risk_score))  # Clamp to 0-10


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


def _ensure_required_scores(parsed: DocumentAnalysis) -> DocumentAnalysis:
    """
    Validate scores returned by the LLM and recalculate the headline risk.

    Missing score keys are left absent — the LLM is instructed to omit scores it
    cannot assess from the extraction. Invalid values (out-of-range or wrong type)
    are dropped so they don't distort the weighted risk formula.
    """
    cleaned: dict[str, DocumentAnalysisScores] = {}
    for score_name, score_obj in parsed.scores.items():
        score_value = getattr(score_obj, "score", None)
        if score_value is not None and isinstance(score_value, int) and 0 <= score_value <= 10:
            cleaned[score_name] = score_obj

    parsed.scores = cleaned

    # Recalculate risk_score and verdict deterministically from whatever scores the LLM
    # returned. _calculate_risk_score handles partial score sets by normalising weights.
    parsed.risk_score = _calculate_risk_score(parsed.scores)
    parsed.verdict = _calculate_verdict(parsed.risk_score)

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


def _format_aggregation_payload(aggregation: Aggregation) -> dict[str, Any]:
    by_category: dict[str, list[dict[str, Any]]] = {}
    for finding in aggregation.findings:
        by_category.setdefault(finding.category, []).append(
            {
                "value": finding.value,
                "documents": finding.documents,
                "attributes": finding.attributes,
            }
        )
    return {
        "findings": by_category,
        "conflicts": [c.model_dump() for c in aggregation.conflicts],
        "coverage": [c.model_dump() for c in (aggregation.coverage or [])],
    }


def should_use_reasoning_model(document: Document) -> bool:
    """
    Determine if a reasoning/complex model should be used for legal analysis.

    This function is provider-agnostic and helps select appropriate model complexity
    based on document characteristics, making it resilient to provider or model changes.
    """
    # Use reasoning models for complex documents or high-stakes document types
    doc_length = len(document.text)
    complex_doc_types = ["terms_of_service", "data_processing_agreement", "terms_and_conditions"]

    # Use reasoning model if document is large (>50K chars) or is a complex type
    return doc_length > 50000 or document.doc_type in complex_doc_types


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
        if "overall_risk" not in risk_breakdown_raw:
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

    raw_sections = data.get("key_sections", [])
    if isinstance(raw_sections, list):
        try:
            analysis.key_sections = [
                DocumentSection.model_validate(s) for s in raw_sections if isinstance(s, dict)
            ]
        except Exception as e:
            logger.warning(f"Failed to parse key_sections: {e}")

    analysis.analysis_completeness = data.get("analysis_completeness", "full")
    raw_gaps = data.get("coverage_gaps", [])
    if isinstance(raw_gaps, list):
        analysis.coverage_gaps = [str(g) for g in raw_gaps if g]

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
) -> DocumentAnalysis | None:
    """
    Summarize a document with caching, retry logic, and optimized model selection.

    Args:
        document: The document to summarize
        use_cache: Whether to check for cached analysis
        max_retries: Maximum number of retry attempts
        cancellation_token: Optional cancellation token for interrupting the operation

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

    if not (document.text or "").strip():
        logger.info(f"Skipping analysis for document {document.id}: no text content")
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

    if extracted_prompt is not None:
        prompt = extracted_prompt
    else:
        # Fallback: raw text path (extraction unavailable)
        doc_text = document.text or ""
        max_chars = 200000

        if len(doc_text) > max_chars:
            logger.warning(
                f"Document {document.id} is very long ({len(doc_text)} chars), truncating for fallback path."
            )
            doc_text = (
                doc_text[: max_chars // 2]
                + "\n\n[... document truncated — set analysis_completeness to 'partial' ...]\n\n"
                + doc_text[-max_chars // 2 :]
            )

        prompt = f"""Document Title: {document.title or "Not specified"}
Document Type: {document.doc_type}
Document URL: {document.url}
Document Regions: {document.regions}
Document Locale: {document.locale or "Not specified"}

Extraction completeness: PARTIAL — structured extraction unavailable, analyzing raw text.
Set analysis_completeness to 'partial' in your response.

Document content:
{doc_text}""".strip()

    last_exception: Exception | None = None

    # Set up usage tracking for this document summarization
    usage_tracker = UsageTracker()
    tracker_callback = usage_tracker.create_tracker("analyse_document")

    for attempt in range(max_retries):
        # Check for cancellation before each retry attempt
        await token.check_cancellation()

        try:
            logger.debug(f"Analysing document {document.id} (attempt {attempt + 1}/{max_retries}) ")

            async with usage_tracking(tracker_callback):
                # Wrap the LLM call in a cancellable task
                llm_task = asyncio.create_task(
                    acompletion_with_fallback(
                        messages=[
                            {
                                "role": "system",
                                "content": DOCUMENT_ANALYSIS_PROMPT,
                            },
                            {"role": "user", "content": prompt},
                        ],
                        response_format={"type": "json_object"},
                        temperature=0,
                    )
                )

                # Wait for either completion or cancellation
                cancellation_task = asyncio.create_task(token.cancelled.wait())
                _, pending = await asyncio.wait(
                    [llm_task, cancellation_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # Cancel pending tasks
                for p in pending:
                    p.cancel()
                    try:
                        await p
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

                parsed: DocumentAnalysis = DocumentAnalysis.model_validate(
                    parsed_dict, strict=False
                )

                # Ensure all required scores are present, normalize names, and calculate risk_score/verdict
                parsed = _ensure_required_scores(parsed)

                # Parse deep analysis fields (critical_clauses, risk_breakdown, key_sections,
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


async def generate_product_overview(
    db: AgnosticDatabase,
    product_slug: str,
    force_regenerate: bool = False,
    product_svc: ProductService | None = None,
    document_svc: DocumentService | None = None,
    cancellation_token: CancellationToken | None = None,
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
    aggregation_service = AggregationService(
        DocumentRepository(), FindingRepository(), AggregationRepository()
    )
    await aggregation_service.rebuild_findings_for_product(db, product.id)
    aggregation = await aggregation_service.build_product_aggregation(
        db, product_id=product.id, product_slug=product_slug
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
                    {"data_type": p.data_type, "purposes": p.purposes}
                    for p in doc.extraction.data_purposes
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

    # Include cross-document conflicts from the aggregation engine.
    # These are deterministically detected facts (e.g., one doc says data is not sold,
    # another says it can be shared with commercial partners) that the LLM should weigh.
    conflicts_section = ""
    if aggregation.conflicts:
        conflicts_section = (
            "\nCross-document conflicts detected by the analysis engine "
            "(report these in the contradictions field):\n"
            + json.dumps([c.model_dump() for c in aggregation.conflicts], indent=2)
            + "\n"
        )

    prompt = f"""Product: {product_slug}
Core documents analyzed: {len(doc_inputs)} of {len(core_docs)} core documents
Document types: {", ".join(doc.doc_type for doc in core_docs if doc.analysis)}
{conflicts_section}
Per-document analyses and extractions:
{json.dumps(doc_inputs, indent=2)}
"""

    # Set up usage tracking for meta-summary generation
    usage_tracker = UsageTracker()
    tracker_callback = usage_tracker.create_tracker("generate_overview")

    # Check for cancellation before making LLM call
    await token.check_cancellation()

    try:
        async with usage_tracking(tracker_callback):
            # Wrap the LLM call in a cancellable task
            llm_task = asyncio.create_task(
                acompletion_with_fallback(
                    messages=[
                        {
                            "role": "system",
                            "content": PRODUCT_OVERVIEW_PROMPT,
                        },
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                )
            )

            # Wait for either completion or cancellation
            cancellation_task = asyncio.create_task(token.cancelled.wait())
            done, pending = await asyncio.wait(
                [llm_task, cancellation_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Cancel pending tasks
            for p in pending:
                p.cancel()
                try:
                    await p
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

        # Parse contradictions before model validation
        raw_contradictions = overview_dict.pop("contradictions", None)

        meta_summary = MetaSummary.model_validate(overview_dict, strict=False)
        meta_summary.coverage = aggregation.coverage

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

        # Product risk_score: deterministic blend of core document analyses (privacy
        # policy weighted highest). LLM overview risk_score is discarded.
        if meta_summary and core_docs:
            blended = _weighted_product_risk_score(core_docs)
            if blended is not None:
                meta_summary.risk_score = blended
                meta_summary.verdict = _calculate_verdict(meta_summary.risk_score)

        # Save to database (simple single-cache entry)
        await product_svc.save_product_overview(
            db,
            product_slug=product_slug,
            meta_summary=meta_summary,
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
                    {"data_type": p.data_type, "purposes": p.purposes}
                    for p in doc.extraction.data_purposes[:20]
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
