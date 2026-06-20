"""Evidence-first structured extraction engine for policy documents (v4 architecture).

**What it does**
Takes a ``Document`` (with cleaned text), splits it into overlapping chunks,
sends each chunk through the LLM with a structured JSON extraction prompt,
parses the per-chunk results, merges them across chunks, and returns a complete
``ExtractionResult`` with evidence quotes and confidence scores.

**What it contains**
- ``extract_document_facts(document, …)``: the main entry point, called by the pipeline.
- ``_extract_chunk(chunk_text, document_type, cluster_keys)``: sends one chunk to
  the LLM and parses the response.
- ``_merge_all(results)``: invokes all ``_merge_*`` functions from ``merging.py``.
- ``_EXTRACTION_PRIMARY``: cluster key for the primary extraction pass.

**What it allows/prevents**
Allows the pipeline to turn a raw policy document into a structured fact set
suitable for summarisation and comparison.  Prevents hallucinations by requiring
every extracted fact to include a supporting quote from the source text.
Prevents context-window overflow by chunking long documents.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from src.core.logging import get_logger
from src.llm import MODEL_PRIORITY, SupportedModel, acompletion_with_fallback
from src.models.document import (
    Document,
    DocumentExtraction,
    ExtractedAIUsage,
    ExtractedChildrenPolicy,
    ExtractedContentOwnership,
    ExtractedCookieTracker,
    ExtractedCorporateFamilySharing,
    ExtractedDataItem,
    ExtractedDataPurposeLink,
    ExtractedDisputeResolution,
    ExtractedGovernmentAccess,
    ExtractedInternationalTransfer,
    ExtractedLiability,
    ExtractedRetentionRule,
    ExtractedScopeExpansion,
    ExtractedTextItem,
    ExtractedThirdPartyRecipient,
    ExtractedUserRight,
    PrivacySignals,
)
from src.services.extraction_service.merging import (
    _clean_raw,
    _merge_ai_usage,
    _merge_children_policy,
    _merge_content_ownership,
    _merge_cookie_trackers,
    _merge_corporate_family,
    _merge_data_items,
    _merge_dispute_resolution,
    _merge_government_access,
    _merge_international_transfers,
    _merge_liability,
    _merge_privacy_signals,
    _merge_purpose_links,
    _merge_retention_rules,
    _merge_scope_expansion,
    _merge_text_items,
    _merge_third_parties,
    _merge_user_rights,
)
from src.services.extraction_service.models import (
    _ClusterDataPractices,
    _ClusterLegalScope,
    _ClusterRightsAI,
    _ClusterSharingTransfers,
)
from src.services.extraction_service.prompts import (
    CLUSTER_NAMES,
    EXTRACTION_SYSTEM_PROMPT,
    _get_extraction_prompt,
)
from src.services.extraction_service.utils import (
    _chunk_text,
    _compute_content_hash,
    _extraction_validator,
)
from src.services.term_materiality_classifier import enrich_extraction_materiality
from src.utils.cancellation import CancellationToken

logger = get_logger(__name__)

_EXTRACTION_PRIMARY: list[SupportedModel] = MODEL_PRIORITY


async def extract_document_facts(
    document: Document,
    *,
    use_cache: bool = True,
    cancellation_token: CancellationToken | None = None,
) -> DocumentExtraction:
    """Extract evidence-backed facts from a document."""
    token = cancellation_token or CancellationToken()
    logger.debug(f"Starting v4 extraction for document {document.id} (use_cache={use_cache})")

    content_hash = (
        document.metadata.get("content_hash") if document.metadata else None
    ) or _compute_content_hash(document)

    if (
        use_cache
        and document.extraction
        and document.extraction.source_content_hash == content_hash
        and document.extraction.version == "v4"
    ):
        logger.debug(f"Using cached v4 extraction for document {document.id}")
        return document.extraction

    text = document.text or ""
    chunks = _chunk_text(text, chunk_size=8000, overlap=800)
    logger.debug(f"Chunked document {document.id} into {len(chunks)} chunk(s)")

    if not chunks:
        extraction = DocumentExtraction(
            version="v4",
            generated_at=datetime.now(),
            source_content_hash=content_hash,
        )
        document.extraction = extraction
        return extraction

    data_collected: dict[str, ExtractedDataItem] = {}
    data_purposes: dict[str, ExtractedDataPurposeLink] = {}
    retention_policies: dict[str, ExtractedRetentionRule] = {}
    security_measures: dict[str, ExtractedTextItem] = {}
    cookies_and_trackers: dict[str, ExtractedCookieTracker] = {}

    third_party_details: dict[str, ExtractedThirdPartyRecipient] = {}
    international_transfers: dict[str, ExtractedInternationalTransfer] = {}
    government_access: dict[str, ExtractedGovernmentAccess] = {}
    corporate_family_sharing: dict[str, ExtractedCorporateFamilySharing] = {}

    user_rights: dict[str, ExtractedUserRight] = {}
    consent_mechanisms: dict[str, ExtractedTextItem] = {}
    account_lifecycle: dict[str, ExtractedTextItem] = {}
    ai_usage: dict[str, ExtractedAIUsage] = {}
    children_policy: ExtractedChildrenPolicy | None = None

    liability: dict[str, ExtractedLiability] = {}
    dispute_resolution: dict[str, ExtractedDisputeResolution] = {}
    content_ownership: dict[str, ExtractedContentOwnership] = {}
    scope_expansion: dict[str, ExtractedScopeExpansion] = {}
    indemnification: dict[str, ExtractedTextItem] = {}
    termination_consequences: dict[str, ExtractedTextItem] = {}
    dangers: dict[str, ExtractedTextItem] = {}
    benefits: dict[str, ExtractedTextItem] = {}
    recommended_actions: dict[str, ExtractedTextItem] = {}

    accumulated_signals = PrivacySignals()

    async def _run_cluster(cluster_name: str, chunk_text: str, chunk_idx: int) -> dict[str, Any]:
        logger.debug(
            f"Running cluster '{cluster_name}' for {document.id} chunk {chunk_idx}/{len(chunks)}"
        )
        messages = [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _get_extraction_prompt(document, chunk_text, cluster_name),
            },
        ]
        response = await acompletion_with_fallback(
            messages,
            model_priority=_EXTRACTION_PRIMARY,
            validator=_extraction_validator(cluster_name),
            response_format={"type": "json_object"},
        )
        logger.info(
            "Cluster '%s' for %s chunk %d completed with model %s",
            cluster_name,
            document.id,
            chunk_idx,
            response.model,
        )
        choice = response.choices[0]
        if not hasattr(choice, "message"):
            raise ValueError("Unexpected response format: missing message attribute")
        message = choice.message
        if not message:
            raise ValueError("Unexpected response format: message is None")
        content = message.content
        if not content:
            raise ValueError("Empty response from LLM")
        return json.loads(content)

    chunk_semaphore = asyncio.Semaphore(5)
    merge_lock = asyncio.Lock()

    async def _process_chunk(idx: int, chunk: str) -> None:
        await token.check_cancellation()
        async with chunk_semaphore:
            logger.debug(
                f"Extracting v4 facts for {document.id}: chunk {idx}/{len(chunks)} (4 parallel clusters)"
            )

            results = await asyncio.gather(
                *(_run_cluster(name, chunk, idx) for name in CLUSTER_NAMES),
                return_exceptions=True,
            )

        safe: list[dict[str, Any]] = []
        for i, result in enumerate(results):
            if isinstance(result, BaseException):
                logger.warning(
                    f"Cluster '{CLUSTER_NAMES[i]}' failed for {document.id} chunk {idx}: {result}"
                )
                safe.append({})
            else:
                safe.append(_clean_raw(result))

        dp_raw, st_raw, ra_raw, ls_raw = safe

        try:
            dp = _ClusterDataPractices.model_validate(dp_raw, strict=False)
        except Exception as e:
            logger.warning(f"Validation failed for data_practices chunk {idx}: {e}")
            dp = _ClusterDataPractices()
        try:
            st = _ClusterSharingTransfers.model_validate(st_raw, strict=False)
        except Exception as e:
            logger.warning(f"Validation failed for sharing_transfers chunk {idx}: {e}")
            st = _ClusterSharingTransfers()
        try:
            ra = _ClusterRightsAI.model_validate(ra_raw, strict=False)
        except Exception as e:
            logger.warning(f"Validation failed for rights_ai chunk {idx}: {e}")
            ra = _ClusterRightsAI()
        try:
            ls = _ClusterLegalScope.model_validate(ls_raw, strict=False)
        except Exception as e:
            logger.warning(f"Validation failed for legal_scope chunk {idx}: {e}")
            ls = _ClusterLegalScope()

        nonlocal children_policy

        async with merge_lock:
            _merge_data_items(
                data_collected, dp.data_collected, document=document, content_hash=content_hash
            )
            _merge_purpose_links(
                data_purposes, dp.data_purposes, document=document, content_hash=content_hash
            )
            _merge_retention_rules(
                retention_policies,
                dp.retention_policies,
                document=document,
                content_hash=content_hash,
            )
            _merge_text_items(
                security_measures,
                dp.security_measures,
                document=document,
                content_hash=content_hash,
            )
            _merge_cookie_trackers(
                cookies_and_trackers,
                dp.cookies_and_trackers,
                document=document,
                content_hash=content_hash,
            )

            _merge_third_parties(
                third_party_details,
                st.third_party_details,
                document=document,
                content_hash=content_hash,
            )
            _merge_international_transfers(
                international_transfers,
                st.international_transfers,
                document=document,
                content_hash=content_hash,
            )
            _merge_government_access(
                government_access,
                st.government_access,
                document=document,
                content_hash=content_hash,
            )
            _merge_corporate_family(
                corporate_family_sharing,
                st.corporate_family_sharing,
                document=document,
                content_hash=content_hash,
            )

            _merge_user_rights(
                user_rights, ra.user_rights, document=document, content_hash=content_hash
            )
            _merge_text_items(
                consent_mechanisms,
                ra.consent_mechanisms,
                document=document,
                content_hash=content_hash,
            )
            _merge_text_items(
                account_lifecycle,
                ra.account_lifecycle,
                document=document,
                content_hash=content_hash,
            )
            _merge_ai_usage(ai_usage, ra.ai_usage, document=document, content_hash=content_hash)
            children_policy = _merge_children_policy(
                children_policy, ra.children_policy, document=document, content_hash=content_hash
            )
            _merge_privacy_signals(
                accumulated_signals,
                ra.privacy_signals,
                document=document,
                content_hash=content_hash,
            )

            _merge_liability(liability, ls.liability, document=document, content_hash=content_hash)
            _merge_dispute_resolution(
                dispute_resolution,
                ls.dispute_resolution,
                document=document,
                content_hash=content_hash,
            )
            _merge_content_ownership(
                content_ownership,
                ls.content_ownership,
                document=document,
                content_hash=content_hash,
            )
            _merge_scope_expansion(
                scope_expansion, ls.scope_expansion, document=document, content_hash=content_hash
            )
            _merge_text_items(
                indemnification, ls.indemnification, document=document, content_hash=content_hash
            )
            _merge_text_items(
                termination_consequences,
                ls.termination_consequences,
                document=document,
                content_hash=content_hash,
            )
            _merge_text_items(dangers, ls.dangers, document=document, content_hash=content_hash)
            _merge_text_items(benefits, ls.benefits, document=document, content_hash=content_hash)
            _merge_text_items(
                recommended_actions,
                ls.recommended_actions,
                document=document,
                content_hash=content_hash,
            )

    chunk_results = await asyncio.gather(
        *(_process_chunk(idx, chunk) for idx, chunk in enumerate(chunks, 1)),
        return_exceptions=True,
    )
    failed_chunks = 0
    for i, result in enumerate(chunk_results):
        if isinstance(result, BaseException):
            failed_chunks += 1
            logger.warning(f"Chunk {i + 1}/{len(chunks)} failed for {document.id}: {result}")
    if failed_chunks:
        logger.warning(f"{failed_chunks}/{len(chunks)} chunks failed for {document.id}")

    extraction = DocumentExtraction(
        version="v4",
        generated_at=datetime.now(),
        source_content_hash=content_hash,
        data_collected=list(data_collected.values()),
        data_purposes=list(data_purposes.values()),
        retention_policies=list(retention_policies.values()),
        security_measures=list(security_measures.values()),
        cookies_and_trackers=list(cookies_and_trackers.values()),
        third_party_details=list(third_party_details.values()),
        international_transfers=list(international_transfers.values()),
        government_access=list(government_access.values()),
        corporate_family_sharing=list(corporate_family_sharing.values()),
        user_rights=list(user_rights.values()),
        consent_mechanisms=list(consent_mechanisms.values()),
        account_lifecycle=list(account_lifecycle.values()),
        ai_usage=list(ai_usage.values()),
        children_policy=children_policy,
        liability=list(liability.values()),
        dispute_resolution=list(dispute_resolution.values()),
        content_ownership=list(content_ownership.values()),
        scope_expansion=list(scope_expansion.values()),
        indemnification=list(indemnification.values()),
        termination_consequences=list(termination_consequences.values()),
        privacy_signals=accumulated_signals,
        dangers=list(dangers.values()),
        benefits=list(benefits.values()),
        recommended_actions=list(recommended_actions.values()),
    )

    await enrich_extraction_materiality(extraction)

    logger.debug(
        f"v4 extraction complete for {document.id}: "
        f"data={len(extraction.data_collected)}, rights={len(extraction.user_rights)}, "
        f"ai={len(extraction.ai_usage)}, liability={len(extraction.liability)}, "
        f"scope_expansion={len(extraction.scope_expansion)}, "
        f"content_ownership={len(extraction.content_ownership)}"
    )

    document.extraction = extraction
    document.metadata["extraction_version"] = extraction.version
    document.metadata["extraction_generated_at"] = extraction.generated_at.isoformat()
    document.metadata["extraction_source_hash"] = content_hash

    return extraction


__all__ = [
    "_EXTRACTION_PRIMARY",
    "extract_document_facts",
]
