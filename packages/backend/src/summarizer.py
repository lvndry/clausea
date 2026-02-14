"""Document summarization module for privacy-focused analysis of legal documents."""

import asyncio
import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from dotenv import load_dotenv
from motor.core import AgnosticDatabase

from src.core.logging import get_logger
from src.llm import acompletion_with_fallback
from src.models.document import (
    BusinessImpact,
    BusinessImpactAssessment,
    CrossDocumentAnalysis,
    Document,
    DocumentAnalysis,
    DocumentAnalysisScores,
    DocumentDeepAnalysis,
    DocumentRiskBreakdown,
    EnhancedComplianceBreakdown,
    IndividualImpact,
    MetaSummary,
    ProductDeepAnalysis,
    RiskPrioritization,
)
from src.prompts.summarizer_prompts import (
    AGGREGATE_DEEP_ANALYSIS_PROMPT,
    DOCUMENT_SUMMARY_SYSTEM_PROMPT,
    PRODUCT_OVERVIEW_SYSTEM_PROMPT,
    SINGLE_DOC_DEEP_ANALYSIS_PROMPT,
)
from src.services.document_service import DocumentService
from src.services.extraction_service import extract_document_facts
from src.services.product_service import ProductService
from src.utils.cancellation import CancellationToken
from src.utils.llm_usage import UsageTracker, log_usage_summary, usage_tracking

load_dotenv()
logger = get_logger(__name__)


async def summarize_all_product_documents(
    db: AgnosticDatabase,
    product_slug: str,
    document_svc: DocumentService,
    cancellation_token: CancellationToken | None = None,
) -> list[Document]:
    """Summarize all documents for a product with cancellation support."""
    # For HTTP requests, create a fresh token if none provided
    # The global token is for signal-based cancellation (Ctrl+C) and may be in a cancelled state
    if cancellation_token is None:
        token = CancellationToken()
    else:
        token = cancellation_token

    documents: list[Document] = await document_svc.get_product_documents_by_slug(db, product_slug)
    total_docs: int = len(documents)
    logger.info(f"Summarizing {total_docs} documents for {product_slug}")

    for index, doc in enumerate(documents, 1):
        # Check for cancellation before processing each document
        await token.check_cancellation()

        logger.info(f"Processing document {index}/{total_docs}: {doc.title}")
        try:
            analysis = await summarize_document(doc, cancellation_token=token)
            if analysis:
                doc.analysis = analysis
                await document_svc.update_document(db, doc)
                logger.info(f"✓ Stored analysis for document {doc.id}")
            else:
                logger.warning(f"✗ Failed to generate analysis for document {doc.id}")
        except asyncio.CancelledError:
            logger.info(f"Summarization cancelled at document {index}/{total_docs}")
            raise

    logger.info(f"✓ Successfully summarized all {total_docs} documents for {product_slug}")
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
    Uses weighted average: transparency (20%), data_collection_scope (25%), user_control (25%), third_party_sharing (30%)
    Lower component scores = higher risk, so risk_score = 10 - weighted_average
    """
    weights = {
        "transparency": 0.20,
        "data_collection_scope": 0.25,
        "user_control": 0.25,
        "third_party_sharing": 0.30,
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


def _ensure_required_scores(parsed: DocumentAnalysis) -> DocumentAnalysis:
    """
    Ensure all required scores are present and calculate risk_score/verdict if missing.
    """
    # Ensure all required core scores are present
    required_scores = [
        "transparency",
        "data_collection_scope",
        "user_control",
        "third_party_sharing",
    ]
    for score_name in required_scores:
        if score_name not in parsed.scores:
            parsed.scores[score_name] = DocumentAnalysisScores(
                score=0, justification="Score not provided by model"
            )

    # Ensure optional scores (data_retention_score, security_score) are always present
    # These are required in the schema but may be missing or have null values
    optional_scores = ["data_retention_score", "security_score"]
    for score_name in optional_scores:
        if score_name not in parsed.scores:
            # Add missing score with default value
            parsed.scores[score_name] = DocumentAnalysisScores(
                score=5, justification="Not specified in document"
            )
        else:
            score_obj = parsed.scores[score_name]
            # Only replace if score is None or invalid (not an integer or out of range)
            score_value = getattr(score_obj, "score", None)
            if (
                score_value is None
                or not isinstance(score_value, int)
                or not (0 <= score_value <= 10)
            ):
                # Invalid score - replace with default
                parsed.scores[score_name] = DocumentAnalysisScores(
                    score=5,  # Default middle score if not specified
                    justification=(
                        score_obj.justification
                        if score_obj
                        and hasattr(score_obj, "justification")
                        and score_obj.justification
                        else "Not specified in document"
                    ),
                )
            # Otherwise, keep the valid LLM-provided score (only update justification if missing)
            elif not score_obj.justification:
                # Keep the score but ensure justification is present
                parsed.scores[score_name] = DocumentAnalysisScores(
                    score=score_value, justification="Not specified in document"
                )

    # Calculate risk_score if not provided
    if not hasattr(parsed, "risk_score"):
        parsed.risk_score = _calculate_risk_score(parsed.scores)

    # Calculate verdict if not provided or doesn't match risk_score
    if not hasattr(parsed, "verdict"):
        parsed.verdict = _calculate_verdict(parsed.risk_score)
    else:
        # Verify verdict matches risk_score (recalculate if mismatch)
        expected_verdict = _calculate_verdict(parsed.risk_score)
        if parsed.verdict != expected_verdict:
            logger.warning(
                f"Verdict '{parsed.verdict}' doesn't match risk_score {parsed.risk_score}, "
                f"recalculating to '{expected_verdict}'"
            )
            parsed.verdict = expected_verdict

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
        "your_rights",
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
            value = str(item.get("value") or "").strip()
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


async def summarize_document(
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
        DocumentAnalysis or None if summarization fails

    Raises:
        asyncio.CancelledError: If cancellation is requested
    """
    # For HTTP requests, create a fresh token if none provided
    # The global token is for signal-based cancellation (Ctrl+C) and may be in a cancelled state
    if cancellation_token is None:
        token = CancellationToken()
    else:
        token = cancellation_token
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

    # Evidence-first: extract structured facts WITH quotes, then generate analysis only from extracted facts.
    # Fallback to raw text only if extraction fails unexpectedly.
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
        extracted_prompt = f"""
Document Title: {document.title or "Not specified"}
Document Type: {document.doc_type}
Document URL: {document.url}
Document Regions: {document.regions}
Document Locale: {document.locale or "Not specified"}

CRITICAL REQUIREMENT:
- Use ONLY the extracted facts below. Do NOT add any new data types, purposes, rights, third parties, or claims that are not present in the extracted facts.
- If something is missing from the extracted facts, explicitly say "Not specified in document" (or equivalent).

Extracted facts (evidence-backed JSON):
{extraction.model_dump_json()}
""".strip()
    except Exception as e:
        logger.warning(
            f"Extraction failed for document {document.id}: {e}. Falling back to raw text."
        )

    if extracted_prompt is not None:
        prompt = extracted_prompt
    else:
        # Prepare document content (legacy fallback path)
        doc_text = document.text
        max_tokens = 200000  # Approximate token limit (roughly 4 chars per token)

        if len(doc_text) > max_tokens:
            logger.warning(
                f"Document {document.id} is very long ({len(doc_text)} chars). "
                "Consider implementing chunking for better results."
            )
            doc_text = (
                doc_text[: max_tokens // 2]
                + "\n\n[... document truncated ...]\n\n"
                + doc_text[-max_tokens // 2 :]
            )

        prompt = f"""
Document Title: {document.title or "Not specified"}
Document Type: {document.doc_type}
Document URL: {document.url}
Document Regions: {document.regions}
Document Locale: {document.locale or "Not specified"}

**IMPORTANT: Determine document scope from the above metadata and content below.**
Consider if this is a global policy, product-specific, region-specific, or service-specific document.

Document content:
{doc_text}
""".strip()

    # Select appropriate model based on document complexity

    last_exception: Exception | None = None

    # Set up usage tracking for this document summarization
    usage_tracker = UsageTracker()
    tracker_callback = usage_tracker.create_tracker("summarize_document")

    for attempt in range(max_retries):
        # Check for cancellation before each retry attempt
        await token.check_cancellation()

        try:
            logger.debug(
                f"Summarizing document {document.id} (attempt {attempt + 1}/{max_retries}) "
            )

            async with usage_tracking(tracker_callback):
                # Wrap the LLM call in a cancellable task
                llm_task = asyncio.create_task(
                    acompletion_with_fallback(
                        messages=[
                            {
                                "role": "system",
                                "content": DOCUMENT_SUMMARY_SYSTEM_PROMPT,
                            },
                            {"role": "user", "content": prompt},
                        ],
                        response_format={"type": "json_object"},
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
                    raise asyncio.CancelledError("Document summarization cancelled")

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
            summary_data = content
            if not summary_data:
                raise ValueError("Empty response from LLM")

            # Parse and validate response
            try:
                # First parse as dict to handle null scores before validation
                parsed_dict = json.loads(summary_data)

                # Fix null scores for data_retention_score and security_score
                if "scores" in parsed_dict:
                    for score_name in ["data_retention_score", "security_score"]:
                        if score_name in parsed_dict["scores"]:
                            score_obj = parsed_dict["scores"][score_name]
                            if score_obj is None or (
                                isinstance(score_obj, dict) and score_obj.get("score") is None
                            ):
                                parsed_dict["scores"][score_name] = {
                                    "score": 5,
                                    "justification": "Not specified in document",
                                }
                            elif (
                                isinstance(score_obj, dict)
                                and "score" in score_obj
                                and score_obj["score"] is None
                            ):
                                parsed_dict["scores"][score_name]["score"] = 5
                                if not parsed_dict["scores"][score_name].get("justification"):
                                    parsed_dict["scores"][score_name]["justification"] = (
                                        "Not specified in document"
                                    )

                # Now validate the cleaned dict
                parsed: DocumentAnalysis = DocumentAnalysis.model_validate(
                    parsed_dict, strict=False
                )

                # Ensure all required scores are present, normalize names, and calculate risk_score/verdict
                parsed = _ensure_required_scores(parsed)

                # Attach evidence spans to keypoints when possible (best-effort)
                _attach_keypoint_evidence(parsed, extraction_for_evidence)

                # Store content hash in metadata for future cache validation
                content_hash = _compute_document_hash(document)

                document.metadata["content_hash"] = content_hash
                document.metadata["analysis_hash_stored_at"] = datetime.now().isoformat()

                logger.info(
                    f"Successfully summarized document {document.id} (hash: {content_hash[:8]}...)"
                )

                # Log LLM usage for this document summarization (success case)
                summary, records = usage_tracker.consume_summary()
                log_usage_summary(
                    summary,
                    records,
                    context=f"document_{document.id}",
                    reason="success",
                    operation_type="summarization",
                    product_id=document.product_id,
                    document_id=document.id,
                    document_url=document.url,
                    document_title=document.title,
                )

                return parsed

            except Exception as parse_error:
                logger.warning(f"Failed to parse LLM response: {parse_error}")
                # Fallback: create minimal valid structure
                fallback_scores = {
                    "transparency": DocumentAnalysisScores(
                        score=0, justification="Analysis parsing failed"
                    ),
                    "data_collection_scope": DocumentAnalysisScores(
                        score=0, justification="Analysis parsing failed"
                    ),
                    "user_control": DocumentAnalysisScores(
                        score=0, justification="Analysis parsing failed"
                    ),
                    "third_party_sharing": DocumentAnalysisScores(
                        score=0, justification="Analysis parsing failed"
                    ),
                }
                parsed_fallback: DocumentAnalysis = DocumentAnalysis(
                    summary=summary_data[:500] if summary_data else "Analysis unavailable",
                    scores=fallback_scores,
                    risk_score=5,  # Default middle risk score
                    verdict="moderate",  # Default verdict
                    keypoints=[],
                )

                # Log LLM usage even for fallback case
                summary, records = usage_tracker.consume_summary()
                log_usage_summary(
                    summary,
                    records,
                    context=f"document_{document.id}",
                    reason="parsing_fallback",
                    operation_type="summarization",
                    product_id=document.product_id,
                    document_id=document.id,
                    document_url=document.url,
                    document_title=document.title,
                )

                return parsed_fallback

        except asyncio.CancelledError:
            # Re-raise cancellation errors immediately
            logger.info(f"Document summarization cancelled for {document.id}")
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

    # All retries failed - log usage even on failure
    summary, records = usage_tracker.consume_summary()
    log_usage_summary(
        summary,
        records,
        context=f"document_{document.id}",
        reason="failed",
        operation_type="summarization",
        document_id=document.id,
        document_url=document.url,
        document_title=document.title,
    )

    logger.error(
        f"Failed to summarize document {document.id} after {max_retries} attempts: {last_exception}"
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
    Generate a cached product overview based on all analyzed documents for a product.

    This is intentionally simple right now:
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
    prod_svc = product_svc
    doc_svc = document_svc

    documents = await doc_svc.get_product_documents_by_slug(db, product_slug)
    logger.info(f"Generating product overview for {product_slug} with {len(documents)} documents")

    # Check cache unless force_regenerate is True
    if not force_regenerate:
        cached_overview_data = await prod_svc.get_product_overview_data(db, product_slug)
        if cached_overview_data and cached_overview_data.get("overview"):
            cached = cached_overview_data["overview"]
            logger.info(f"Using cached product overview for {product_slug}")
            try:
                return MetaSummary.model_validate(cached)
            except Exception as e:
                logger.warning(
                    f"Failed to parse cached product overview for {product_slug}: {e}. Regenerating..."
                )

    # Cache miss or invalid - generate new meta-summary
    logger.info(f"Generating new product overview for {product_slug}")

    summaries = []
    for doc in documents:
        # Check for cancellation before processing each document
        await token.check_cancellation()

        doc_type = doc.doc_type

        # Ensure we have an analysis (use existing or generate)
        analysis = doc.analysis
        if not analysis:
            logger.info(f"Generating analysis for document {doc.id} ({doc.title})")
            try:
                analysis = await summarize_document(doc, cancellation_token=token)
            except asyncio.CancelledError:
                logger.info(f"Meta-summary generation cancelled for {product_slug}")
                raise
            if analysis:
                # Store the analysis in the database
                doc.analysis = analysis
                await doc_svc.update_document(db, doc)
                logger.info(f"✓ Stored analysis for document {doc.id}")

        # Format the analysis text (or add placeholder if no analysis)
        if analysis:
            summary = analysis.summary
            keypoints = analysis.keypoints
            analysis_text = f"""Document Type: {doc_type}
Summary: {summary}

"""
            if keypoints:
                analysis_text += "\nKey Points:\n"
                for point in keypoints:
                    analysis_text += f"  • {point}\n"
            summaries.append(analysis_text)
        else:
            logger.warning(f"Failed to generate analysis for document {doc.id}")
            summaries.append(f"Document Type: {doc_type}\nNo analysis available\n")

    document_summaries = "\n---\n".join(summaries)
    logger.debug(f"Document summaries: {document_summaries}")

    num_documents = len(documents)
    document_types = list({doc.doc_type for doc in documents})

    prompt = f"""
Your task is to create a clear, comprehensive overview that gives users immediate, actionable insights about their privacy and rights. Synthesize information from the following {num_documents} document(s) ({", ".join(document_types)}) into a unified picture.

**CRITICAL REQUIREMENTS:**
1. **Summary field (MOST IMPORTANT)**: Write a clear, comprehensive paragraph (4-6 sentences) that:
   - Starts directly with the information (e.g., "This platform collects...", "Users have the right to...")
   - Synthesizes insights from ALL documents into a unified picture
   - Explains what data is collected, key privacy concerns/protections, user control, and overall privacy posture
   - Focuses on actionable insights and real-world impact
   - DO NOT mention "we analyzed" or describe the analysis process - just present the information directly

2. **Be COMPREHENSIVE**: Extract and aggregate information from ALL documents - don't miss any data types, purposes, or rights mentioned

3. **Be EXPLICIT AND EXPLANATORY**: Specify exact data types (not "personal information" but "email address, IP address, location data") AND explain what each means for users in real life

4. **Be SPECIFIC AND HELPFUL**: For user rights, include WHAT data, WHY it matters, HOW to exercise, and WHERE to go (URLs, email addresses, specific steps)

5. **Be BALANCED**: Clearly highlight both concerning practices (dangers) AND positive privacy protections (benefits), always explaining the impact on users

6. **Synthesize, don't list**: Combine information from all documents into a unified picture - don't list what each document says separately

7. **Explain user impact**: For every fact, explain what it means for someone's daily life, privacy, and control

The following document summaries are provided:

{document_summaries}

Create a unified overview that provides complete value in under 5 minutes of reading. Write clearly and directly.focus on giving users the information they need to understand their privacy and make informed decisions. Make sure anyone, regardless of their privacy knowledge, can understand and get value from your overview.
"""

    # Set up usage tracking for meta-summary generation
    usage_tracker = UsageTracker()
    tracker_callback = usage_tracker.create_tracker("generate_product_overview")

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
                            "content": PRODUCT_OVERVIEW_SYSTEM_PROMPT,
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

        # Parse the meta-summary
        meta_summary = MetaSummary.model_validate_json(content, strict=False)

        # Save to database (simple single-cache entry)
        await prod_svc.save_product_overview(
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


async def _generate_single_document_deep_analysis(
    document: Document,
    usage_tracker: UsageTracker,
) -> DocumentDeepAnalysis | None:
    """
    Generate deep analysis for a single document.
    """
    if not document.analysis:
        logger.warning(f"Document {document.id} has no analysis, skipping deep analysis")
        return None

    # Check if document has text
    if not document.text or len(document.text.strip()) == 0:
        logger.warning(f"Document {document.id} has no text content, skipping deep analysis")
        return None

    # Safely extract text (handle potential None or empty string)
    text_preview = document.text[:15000] if len(document.text) > 15000 else document.text

    prompt = f"""
Document: {document.title or document.doc_type}
Type: {document.doc_type}
URL: {document.url}
Effective Date: {document.effective_date}
Locale: {document.locale}
Regions: {document.regions}

**IMPORTANT: Determine document scope from title, URL, content, and regions:**
- Title: {document.title}
- URL: {document.url}
- Regions: {document.regions}
- Consider if this is a global policy, product-specific, region-specific, or service-specific document

Document Text (first 15,000 characters):
{text_preview}

Existing Analysis:
{document.analysis.model_dump_json()}
"""

    tracker_callback = usage_tracker.create_tracker("single_doc_deep_analysis")

    try:
        async with usage_tracking(tracker_callback):
            response = await acompletion_with_fallback(
                messages=[
                    {
                        "role": "system",
                        "content": SINGLE_DOC_DEEP_ANALYSIS_PROMPT,
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
            )

        import json

        choice = response.choices[0]
        if not hasattr(choice, "message"):
            raise ValueError("Unexpected response format: missing message attribute")
        message = choice.message  # type: ignore[attr-defined]
        if not message:
            raise ValueError("Unexpected response format: message is None")
        content = message.content  # type: ignore[attr-defined]
        if not content:
            raise ValueError("Empty response from LLM")

        data = json.loads(content)

        # Safely construct DocumentRiskBreakdown with defaults if needed
        risk_breakdown_data = data.get("document_risk_breakdown", {})
        if not isinstance(risk_breakdown_data, dict):
            risk_breakdown_data = {}
        # Ensure overall_risk is present and valid
        if "overall_risk" not in risk_breakdown_data:
            # Default to the document's existing risk score if available
            risk_breakdown_data["overall_risk"] = (
                document.analysis.risk_score if document.analysis else 5
            )

        try:
            document_risk_breakdown = DocumentRiskBreakdown(**risk_breakdown_data)
        except Exception as e:
            logger.warning(
                f"Failed to parse document_risk_breakdown for document {document.id}: {e}. Using defaults."
            )
            # Fallback to a safe default
            document_risk_breakdown = DocumentRiskBreakdown(
                overall_risk=document.analysis.risk_score if document.analysis else 5,
                risk_by_category=risk_breakdown_data.get("risk_by_category", {}),
                top_concerns=risk_breakdown_data.get("top_concerns", []),
                positive_protections=risk_breakdown_data.get("positive_protections", []),
                missing_information=risk_breakdown_data.get("missing_information", []),
            )

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
            critical_clauses=data.get("critical_clauses", []),
            document_risk_breakdown=document_risk_breakdown,
            key_sections=data.get("key_sections", []),
        )
    except Exception as e:
        logger.error(f"Error generating deep analysis for document {document.id}: {e}")
        return None


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
    prod_svc = product_svc
    doc_svc = document_svc

    # First ensure we have Level 2 analysis
    analysis = await prod_svc.get_product_analysis(db, product_slug)
    if not analysis:
        # Generate meta-summary first (which creates Level 2)
        logger.info(f"Level 2 analysis not found for {product_slug}, generating...")
        await generate_product_overview(
            db, product_slug=product_slug, product_svc=prod_svc, document_svc=doc_svc
        )
        analysis = await prod_svc.get_product_analysis(db, product_slug)
        if not analysis:
            raise ValueError(f"Failed to generate Level 2 analysis for {product_slug}")

    # Get all documents with full text
    documents = await doc_svc.get_product_documents_by_slug(db, product_slug)
    if not documents:
        raise ValueError(f"No documents found for {product_slug}")

    logger.info(f"Generating deep analysis for {product_slug} with {len(documents)} documents")

    # Compute document signature for caching
    current_signature = _compute_document_signature(documents)

    # Check cache unless force_regenerate
    if not force_regenerate:
        cached_deep_analysis = await prod_svc.get_deep_analysis(db, product_slug)
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

    # Phase 1: Generate deep analysis for each document
    document_analyses: list[DocumentDeepAnalysis] = []

    # Process documents in parallel (with some concurrency limit implicitly handled by acompletion if needed,
    # but here we'll just use gather for simplicity as we don't have too many docs usually)
    # Ideally we should use a semaphore if there are many documents.

    # For now, let's do it sequentially to avoid rate limits and for better error handling visibility
    # or use a small batch size.

    for doc in documents:
        logger.info(f"Generating deep analysis for document: {doc.title or doc.doc_type}")
        doc_analysis = await _generate_single_document_deep_analysis(doc, usage_tracker)
        if doc_analysis:
            document_analyses.append(doc_analysis)
        else:
            logger.warning(f"Failed to generate deep analysis for {doc.id}")

    if not document_analyses:
        raise ValueError(
            f"Failed to generate deep analysis for any documents for {product_slug}. "
            "This may occur if documents are missing analysis (Level 2) or text content."
        )

    # Phase 2: Aggregate Analysis
    logger.info("Generating aggregate deep analysis...")

    # Prepare input for aggregation
    doc_summaries = []
    for da in document_analyses:
        scope = getattr(da.document_risk_breakdown, "scope", None)
        doc_summaries.append(f"""
Document: {da.title or da.document_type} ({da.document_type})
Scope: {scope or "Not specified"}
Risk Score: {da.document_risk_breakdown.overall_risk}
Top Concerns: {", ".join(da.document_risk_breakdown.top_concerns)}
Critical Clauses: {len(da.critical_clauses)} found
""")

    aggregate_prompt = f"""
Product: {product_slug}
Documents Analyzed: {len(document_analyses)}

Document Summaries:
{"".join(doc_summaries)}

**CRITICAL: When prioritizing risks, consider document scope:**
- Global/product-wide documents: Risks affect all users → prioritize higher
- Product-specific documents: Risks affect only specific product users → prioritize lower (but still important)
- When the same risk appears in multiple documents, prioritize based on scope (global > product-specific)

Perform cross-document analysis, compliance assessment, and business impact analysis based on these findings.
"""

    tracker_callback = usage_tracker.create_tracker("aggregate_deep_analysis")

    try:
        async with usage_tracking(tracker_callback):
            response = await acompletion_with_fallback(
                messages=[
                    {
                        "role": "system",
                        "content": AGGREGATE_DEEP_ANALYSIS_PROMPT,
                    },
                    {"role": "user", "content": aggregate_prompt},
                ],
                response_format={"type": "json_object"},
            )

        import json

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

        # Construct final object
        cross_document_analysis = CrossDocumentAnalysis(
            contradictions=agg_data.get("cross_document_analysis", {}).get("contradictions", []),
            information_gaps=agg_data.get("cross_document_analysis", {}).get(
                "information_gaps", []
            ),
            document_relationships=agg_data.get("cross_document_analysis", {}).get(
                "document_relationships", []
            ),
        )

        enhanced_compliance = {}
        for reg, comp_data in agg_data.get("enhanced_compliance", {}).items():
            try:
                if not isinstance(comp_data, dict):
                    logger.warning(f"Invalid compliance data for {reg}, skipping")
                    continue
                enhanced_compliance[reg] = EnhancedComplianceBreakdown(**comp_data)
            except Exception as e:
                logger.warning(f"Failed to parse compliance data for {reg}: {e}. Skipping.")

        biz_impact_data = agg_data.get("business_impact", {})
        try:
            business_impact = BusinessImpactAssessment(
                for_individuals=IndividualImpact(**biz_impact_data.get("for_individuals", {})),
                for_businesses=BusinessImpact(**biz_impact_data.get("for_businesses", {})),
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

        risk_prior_data = agg_data.get("risk_prioritization", {})
        risk_prioritization = RiskPrioritization(
            critical=risk_prior_data.get("critical", []),
            high=risk_prior_data.get("high", []),
            medium=risk_prior_data.get("medium", []),
            low=risk_prior_data.get("low", []),
        )

        deep_analysis = ProductDeepAnalysis(
            analysis=analysis,
            document_analyses=document_analyses,
            cross_document_analysis=cross_document_analysis,
            enhanced_compliance=enhanced_compliance,
            business_impact=business_impact,
            risk_prioritization=risk_prioritization,
        )

        # Save the result to database
        await prod_svc.save_deep_analysis(
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
    from src.core.database import get_db
    from src.services.service_factory import create_services

    async with get_db() as db:
        product_svc, doc_svc = create_services()

        await summarize_all_product_documents(db, "notion", doc_svc)

        print("Generating product overview:")
        print("=" * 50)
        overview = await generate_product_overview(
            db, "notion", product_svc=product_svc, document_svc=doc_svc
        )
        logger.info(overview)
        print("\n" + "=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
