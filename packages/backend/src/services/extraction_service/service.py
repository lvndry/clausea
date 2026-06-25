"""Stage 1 of the pipeline: turn a policy document into atomic, evidence-backed facts.

Extraction has one job: capture *what the documents say* as discrete, verifiable
facts. It does NOT judge whether a fact is good, bad, or risky — that is the
analysis stage's job, working from these facts. Keeping extraction neutral keeps
it high-recall and unbiased: the extractor is rewarded for completeness and exact
evidence, not for hunting dangers. A fact the extractor drops is one analysis can
never weigh, so the bar is "every materially relevant fact, stated plainly", not
"only the alarming ones".

Approach
--------
Every extracted fact is grounded in an exact substring of the source text (its
evidence quote); items whose quote is not found verbatim are discarded, which is
what prevents hallucination. Facts are organised into clusters (data practices;
sharing & transfers; rights & AI; legal scope) so each LLM call carries a focused
schema, and splits documents into section-aware segments sized to the context
budget of our long-context model cascade.

Steps
-----
1. Split the document into section-aware segments (markdown headers, then
   paragraphs) sized to the available input token budget.
2. For each segment, send the applicable cluster schema(s) to the LLM and require
   structured JSON in which every item carries an exact-substring evidence quote.
3. Parse each segment response into typed extraction items, discarding any item
   whose quote does not appear verbatim in the segment text.
4. Merge items across segments (``merging.py``): deduplicate by normalised value,
   union the evidence spans, and combine per-document attributes.
5. Return an ``ExtractionResult`` of atomic facts with evidence and confidence,
   ready for the analysis stage to interpret.

Entry point: ``extract_document_facts(document, …)``, called by the pipeline.
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
    _compute_content_hash,
    _document_input_token_budget,
    _extraction_validator,
    _plan_extraction_segments,
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

    text = document.markdown or ""
    segments = _plan_extraction_segments(document, text)
    logger.info(
        "Extraction plan for %s: segments=%d chunk_budget=~%d tokens",
        document.id,
        len(segments),
        _document_input_token_budget(document) if segments else 0,
    )

    if not segments:
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

    async def _run_cluster(
        cluster_name: str, segment_text: str, segment_idx: int
    ) -> dict[str, Any]:
        logger.debug(
            f"Running cluster '{cluster_name}' for {document.id} segment {segment_idx}/{len(segments)}"
        )
        messages = [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _get_extraction_prompt(document, segment_text, cluster_name),
            },
        ]
        response = await acompletion_with_fallback(
            messages,
            model_priority=_EXTRACTION_PRIMARY,
            validator=_extraction_validator(cluster_name),
            response_format={"type": "json_object"},
        )
        logger.info(
            "Cluster '%s' for %s segment %d completed with model %s",
            cluster_name,
            document.id,
            segment_idx,
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

    segment_semaphore = asyncio.Semaphore(5)
    merge_lock = asyncio.Lock()

    async def _process_segment(idx: int, segment: str) -> None:
        await token.check_cancellation()
        async with segment_semaphore:
            logger.debug(
                f"Extracting v4 facts for {document.id}: segment {idx}/{len(segments)} "
                "(4 parallel clusters)"
            )

            results = await asyncio.gather(
                *(_run_cluster(name, segment, idx) for name in CLUSTER_NAMES),
                return_exceptions=True,
            )

        safe: list[dict[str, Any]] = []
        for i, result in enumerate(results):
            if isinstance(result, BaseException):
                logger.warning(
                    f"Cluster '{CLUSTER_NAMES[i]}' failed for {document.id} segment {idx}: {result}"
                )
                safe.append({})
            else:
                safe.append(_clean_raw(result))

        dp_raw, st_raw, ra_raw, ls_raw = safe

        try:
            dp = _ClusterDataPractices.model_validate(dp_raw, strict=False)
        except Exception as e:
            logger.warning(f"Validation failed for data_practices segment {idx}: {e}")
            dp = _ClusterDataPractices()
        try:
            st = _ClusterSharingTransfers.model_validate(st_raw, strict=False)
        except Exception as e:
            logger.warning(f"Validation failed for sharing_transfers segment {idx}: {e}")
            st = _ClusterSharingTransfers()
        try:
            ra = _ClusterRightsAI.model_validate(ra_raw, strict=False)
        except Exception as e:
            logger.warning(f"Validation failed for rights_ai segment {idx}: {e}")
            ra = _ClusterRightsAI()
        try:
            ls = _ClusterLegalScope.model_validate(ls_raw, strict=False)
        except Exception as e:
            logger.warning(f"Validation failed for legal_scope segment {idx}: {e}")
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

    segment_results = await asyncio.gather(
        *(_process_segment(idx, segment) for idx, segment in enumerate(segments, 1)),
        return_exceptions=True,
    )
    failed_segments = 0
    for i, result in enumerate(segment_results):
        if isinstance(result, BaseException):
            failed_segments += 1
            logger.warning(f"Segment {i + 1}/{len(segments)} failed for {document.id}: {result}")
    if failed_segments:
        logger.warning(f"{failed_segments}/{len(segments)} segments failed for {document.id}")

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
