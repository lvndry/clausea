"""Accumulates chunk-level LLM extraction outputs into a single coherent ``ExtractionResult``.

**What it does**
The extraction service splits a policy document into chunks, sends each chunk to
the LLM, and gets per-chunk JSON results.  This module merges those partial results
across chunks using merge strategies that vary by field type:
- Yes/no signals: ``_merge_privacy_signals`` — ``yes`` beats ``no`` beats ``unclear``.
- Lists (data items, third parties, trackers): ``_merge_data_items`` — deduplicated
  by value with evidence concatenated.
- Text items (AI usage, children policy): ``_merge_text_items`` — concatenated with
  separator, deduplicating near-identical statements.

**What it contains**
- ``_merge_privacy_signals(current, new_val, quote_field)``: yes/no/unclear merger.
- ``_merge_data_items(current, new_items)``: list merger with dedup by ``value``.
- ``_merge_third_parties``, ``_merge_cookie_trackers``, ``_merge_retention_rules``:
  domain-specific list mergers with different dedup keys.
- ``_merge_ai_usage``, ``_merge_children_policy``: text accumulation mergers.
- ``_clean_raw(raw_text)``: post-merge cleanup of concatenated markdown quotes.
- ``_add_evidence(quote_field)``: records a quote in the extraction metadata.

**What it allows/prevents**
Allows the extraction service to handle arbitrarily long documents by processing
them in model-sized chunks.  Prevents duplicate extraction entries and ensures
evidence quotes are preserved across chunk boundaries.
"""

import difflib
import re
from typing import Any, cast

from src.models.document import (
    Document,
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
from src.services.extraction_service.models import (
    _AIUsage,
    _ChildrenPolicy,
    _ContentOwnership,
    _CookieTracker,
    _CorporateFamily,
    _DataItem,
    _DisputeResolution,
    _GovernmentAccess,
    _InternationalTransfer,
    _Item,
    _Liability,
    _PrivacySignals,
    _PurposeLink,
    _RetentionRule,
    _ScopeExpansion,
    _ThirdParty,
    _UserRight,
)
from src.services.extraction_service.utils import _make_evidence

_SYNONYM_MAP: dict[str, str] = {
    "e-mail": "email",
    "e-mail address": "email address",
    "ip-address": "ip address",
    "phone number": "phone number",
    "telephone number": "phone number",
    "mobile number": "phone number",
    "date of birth": "date of birth",
    "birth date": "date of birth",
    "geolocation": "location",
    "geo-location": "location",
    "gps location": "location",
    "precise location": "location",
    "full name": "name",
    "first name": "name",
    "last name": "name",
    "firstname": "name",
    "lastname": "name",
    "given name": "name",
    "family name": "name",
    "forename": "name",
    "surname": "name",
    "user name": "username",
    "biometric data": "biometrics",
    "biometric information": "biometrics",
    "facial recognition data": "biometrics",
    "health data": "health information",
    "medical information": "health information",
    "genetic data": "genetic information",
    "financial information": "financial data",
    "payment information": "payment data",
    "credit card": "payment data",
    "debit card": "payment data",
    "billing info": "payment data",
    "billing information": "payment data",
    "device id": "device identifier",
    "device information": "device identifier",
    "unique device identifier": "device identifier",
    "advertising id": "ad identifier",
    "ad identifier": "ad identifier",
    "idfa": "ad identifier",
    "login info": "account credentials",
    "login information": "account credentials",
    "account credentials": "account credentials",
    "social security number": "ssn",
    "national id": "government id",
    "passport number": "government id",
    "drivers license": "government id",
    "driver's license": "government id",
    "purchase history": "transaction data",
    "transaction history": "transaction data",
    "shopping history": "transaction data",
    "browsing history": "usage data",
    "search history": "usage data",
    "viewing history": "usage data",
    "watch history": "usage data",
    "click stream": "usage data",
    "clickstream": "usage data",
}

_SYNONYM_KEYS: list[str] = sorted(_SYNONYM_MAP.keys(), key=len, reverse=True)  # type: ignore[type-var]
_SYNONYM_CLOSE_MATCH_CUTOFF = 0.85


def _dedupe_key(value: str) -> str:
    normalized = re.sub(r"\s+", " ", (value or "")).strip().lower()
    exact = _SYNONYM_MAP.get(normalized)
    if exact is not None:
        return exact
    close = difflib.get_close_matches(
        normalized, _SYNONYM_KEYS, n=1, cutoff=_SYNONYM_CLOSE_MATCH_CUTOFF
    )
    if close:
        return _SYNONYM_MAP[close[0]]
    return normalized


def _merge_text_items(
    existing: dict[str, ExtractedTextItem],
    items: list[_Item],
    *,
    document: Document,
    content_hash: str,
) -> None:
    for item in items:
        key = _dedupe_key(item.value)
        if not key:
            continue
        if key not in existing:
            existing[key] = ExtractedTextItem(value=item.value.strip(), evidence=[])
        if item.quote:
            existing[key].evidence.append(_make_evidence(document, content_hash, item.quote))


def _merge_data_items(
    existing: dict[str, ExtractedDataItem],
    items: list[_DataItem],
    *,
    document: Document,
    content_hash: str,
) -> None:
    sensitivity_order = {"low": 0, "medium": 1, "high": 2, "sensitive": 3}
    for item in items:
        key = _dedupe_key(item.data_type)
        if not key:
            continue
        sens = item.sensitivity.strip().lower() if item.sensitivity else "medium"
        if sens not in sensitivity_order:
            sens = "medium"
        req = item.required.strip().lower() if item.required else "unclear"
        if req not in {"required", "optional", "unclear"}:
            req = "unclear"
        if key not in existing:
            existing[key] = ExtractedDataItem(
                data_type=item.data_type.strip(),
                sensitivity=cast(Any, sens),
                required=cast(Any, req),
                evidence=[],
            )
        else:
            cur_sens = sensitivity_order.get(existing[key].sensitivity, 1)
            new_sens = sensitivity_order.get(sens, 1)
            if new_sens > cur_sens:
                existing[key].sensitivity = cast(Any, sens)
            if req == "required":
                existing[key].required = "required"
        if item.quote:
            existing[key].evidence.append(_make_evidence(document, content_hash, item.quote))


def _merge_purpose_links(
    existing: dict[str, ExtractedDataPurposeLink],
    items: list[_PurposeLink],
    *,
    document: Document,
    content_hash: str,
) -> None:
    for item in items:
        key = _dedupe_key(item.data_type)
        if not key:
            continue
        if key not in existing:
            existing[key] = ExtractedDataPurposeLink(
                data_type=item.data_type.strip(), purposes=[], evidence=[]
            )
        for p in item.purposes or []:
            p_norm = re.sub(r"\s+", " ", p).strip()
            if p_norm and p_norm not in existing[key].purposes:
                existing[key].purposes.append(p_norm)
        if item.quote:
            existing[key].evidence.append(_make_evidence(document, content_hash, item.quote))


def _merge_retention_rules(
    existing: dict[str, ExtractedRetentionRule],
    items: list[_RetentionRule],
    *,
    document: Document,
    content_hash: str,
) -> None:
    for item in items:
        key = _dedupe_key(item.data_scope)
        if not key:
            continue
        if key not in existing:
            existing[key] = ExtractedRetentionRule(
                data_scope=item.data_scope.strip(),
                duration=item.duration.strip() if item.duration else "Not specified",
                conditions=item.conditions.strip() if item.conditions else None,
                evidence=[],
            )
        else:
            if item.duration and len(item.duration) > len(existing[key].duration):
                existing[key].duration = item.duration.strip()
        if item.quote:
            existing[key].evidence.append(_make_evidence(document, content_hash, item.quote))


def _merge_cookie_trackers(
    existing: dict[str, ExtractedCookieTracker],
    items: list[_CookieTracker],
    *,
    document: Document,
    content_hash: str,
) -> None:
    valid_categories = {"essential", "analytics", "advertising", "social", "other"}
    for item in items:
        key = _dedupe_key(item.name_or_type)
        if not key:
            continue
        cat = item.category.strip().lower() if item.category else "other"
        if cat not in valid_categories:
            cat = "other"
        if key not in existing:
            existing[key] = ExtractedCookieTracker(
                name_or_type=item.name_or_type.strip(),
                category=cast(Any, cat),
                duration=item.duration.strip() if item.duration else None,
                third_party=item.third_party,
                opt_out_mechanism=item.opt_out_mechanism.strip()
                if item.opt_out_mechanism
                else None,
                evidence=[],
            )
        else:
            if item.third_party:
                existing[key].third_party = True
            if item.opt_out_mechanism and not existing[key].opt_out_mechanism:
                existing[key].opt_out_mechanism = item.opt_out_mechanism.strip()
        if item.quote:
            existing[key].evidence.append(_make_evidence(document, content_hash, item.quote))


def _merge_third_parties(
    existing: dict[str, ExtractedThirdPartyRecipient],
    items: list[_ThirdParty],
    *,
    document: Document,
    content_hash: str,
) -> None:
    for item in items:
        key = _dedupe_key(item.recipient)
        if not key:
            continue
        if key not in existing:
            existing[key] = ExtractedThirdPartyRecipient(
                recipient=item.recipient.strip(),
                data_shared=[],
                purpose=item.purpose.strip() if item.purpose else None,
                risk_level="medium",
                evidence=[],
            )
        for d in item.data_shared or []:
            d_norm = re.sub(r"\s+", " ", d).strip()
            if d_norm and d_norm not in existing[key].data_shared:
                existing[key].data_shared.append(d_norm)
        if item.purpose:
            new_purpose = item.purpose.strip()
            cur_purpose = existing[key].purpose
            if not cur_purpose or len(new_purpose) > len(cur_purpose):
                existing[key].purpose = new_purpose
        if item.risk_level:
            rl = item.risk_level.strip().lower()
            if rl in {"low", "medium", "high"}:
                existing[key].risk_level = cast(Any, rl)
        if item.quote:
            existing[key].evidence.append(_make_evidence(document, content_hash, item.quote))


def _merge_international_transfers(
    existing: dict[str, ExtractedInternationalTransfer],
    items: list[_InternationalTransfer],
    *,
    document: Document,
    content_hash: str,
) -> None:
    for item in items:
        key = _dedupe_key(item.destination)
        if not key:
            continue
        if key not in existing:
            existing[key] = ExtractedInternationalTransfer(
                destination=item.destination.strip(),
                mechanism=item.mechanism.strip() if item.mechanism else None,
                data_types=[],
                evidence=[],
            )
        for dt in item.data_types or []:
            dt_norm = re.sub(r"\s+", " ", dt).strip()
            if dt_norm and dt_norm not in existing[key].data_types:
                existing[key].data_types.append(dt_norm)
        if item.mechanism and not existing[key].mechanism:
            existing[key].mechanism = item.mechanism.strip()
        if item.quote:
            existing[key].evidence.append(_make_evidence(document, content_hash, item.quote))


def _merge_government_access(
    existing: dict[str, ExtractedGovernmentAccess],
    items: list[_GovernmentAccess],
    *,
    document: Document,
    content_hash: str,
) -> None:
    for item in items:
        key = _dedupe_key(f"{item.authority_type}:{item.conditions}")
        if not key:
            continue
        if key not in existing:
            existing[key] = ExtractedGovernmentAccess(
                authority_type=item.authority_type.strip(),
                conditions=item.conditions.strip(),
                data_scope=item.data_scope.strip() if item.data_scope else None,
                evidence=[],
            )
        if item.quote:
            existing[key].evidence.append(_make_evidence(document, content_hash, item.quote))


def _merge_corporate_family(
    existing: dict[str, ExtractedCorporateFamilySharing],
    items: list[_CorporateFamily],
    *,
    document: Document,
    content_hash: str,
) -> None:
    for item in items:
        ent_key = _dedupe_key(
            ",".join(sorted(item.entities)) if item.entities else item.purpose or "unnamed"
        )
        if not ent_key:
            continue
        if ent_key not in existing:
            existing[ent_key] = ExtractedCorporateFamilySharing(
                entities=[e.strip() for e in item.entities],
                data_shared=[],
                purpose=item.purpose.strip() if item.purpose else None,
                evidence=[],
            )
        for d in item.data_shared or []:
            d_norm = re.sub(r"\s+", " ", d).strip()
            if d_norm and d_norm not in existing[ent_key].data_shared:
                existing[ent_key].data_shared.append(d_norm)
        if item.quote:
            existing[ent_key].evidence.append(_make_evidence(document, content_hash, item.quote))


def _merge_user_rights(
    existing: dict[str, ExtractedUserRight],
    items: list[_UserRight],
    *,
    document: Document,
    content_hash: str,
) -> None:
    for item in items:
        key = _dedupe_key(item.right_type)
        if not key:
            continue
        if key not in existing:
            existing[key] = ExtractedUserRight(
                right_type=item.right_type.strip(),
                description=item.description.strip(),
                mechanism=item.mechanism.strip() if item.mechanism else None,
                evidence=[],
            )
        else:
            if item.mechanism and not existing[key].mechanism:
                existing[key].mechanism = item.mechanism.strip()
            if item.description and len(item.description) > len(existing[key].description):
                existing[key].description = item.description.strip()
        if item.quote:
            existing[key].evidence.append(_make_evidence(document, content_hash, item.quote))


def _merge_ai_usage(
    existing: dict[str, ExtractedAIUsage],
    items: list[_AIUsage],
    *,
    document: Document,
    content_hash: str,
) -> None:
    valid_types = {
        "training_on_user_data",
        "automated_decisions",
        "profiling",
        "content_generation",
        "recommendation",
        "moderation",
        "other",
    }
    for item in items:
        ut = item.usage_type.strip().lower() if item.usage_type else "other"
        if ut not in valid_types:
            ut = "other"
        key = f"{ut}:{_dedupe_key(item.description)}"
        if not key:
            continue
        opt = item.opt_out_available.strip().lower() if item.opt_out_available else "unclear"
        if opt not in {"yes", "no", "unclear"}:
            opt = "unclear"
        if key not in existing:
            existing[key] = ExtractedAIUsage(
                usage_type=cast(Any, ut),
                description=item.description.strip(),
                data_involved=[],
                opt_out_available=cast(Any, opt),
                opt_out_mechanism=item.opt_out_mechanism.strip()
                if item.opt_out_mechanism
                else None,
                consequences=item.consequences.strip() if item.consequences else None,
                evidence=[],
            )
        else:
            if opt == "yes":
                existing[key].opt_out_available = "yes"
            if item.opt_out_mechanism and not existing[key].opt_out_mechanism:
                existing[key].opt_out_mechanism = item.opt_out_mechanism.strip()
        for di in item.data_involved or []:
            di_norm = re.sub(r"\s+", " ", di).strip()
            if di_norm and di_norm not in existing[key].data_involved:
                existing[key].data_involved.append(di_norm)
        if item.quote:
            existing[key].evidence.append(_make_evidence(document, content_hash, item.quote))


def _merge_children_policy(
    accumulated: ExtractedChildrenPolicy | None,
    chunk_policy: _ChildrenPolicy | None,
    *,
    document: Document,
    content_hash: str,
) -> ExtractedChildrenPolicy | None:
    if not chunk_policy or (not chunk_policy.quote and chunk_policy.minimum_age is None):
        return accumulated
    if accumulated is None:
        accumulated = ExtractedChildrenPolicy(evidence=[])
    if chunk_policy.minimum_age is not None:
        if accumulated.minimum_age is None or chunk_policy.minimum_age > accumulated.minimum_age:
            accumulated.minimum_age = chunk_policy.minimum_age
    if chunk_policy.parental_consent_required:
        accumulated.parental_consent_required = True
    if chunk_policy.special_protections:
        sp = chunk_policy.special_protections.strip()
        if not accumulated.special_protections or len(sp) > len(accumulated.special_protections):
            accumulated.special_protections = sp
    if chunk_policy.quote:
        accumulated.evidence.append(_make_evidence(document, content_hash, chunk_policy.quote))
    return accumulated


def _merge_liability(
    existing: dict[str, ExtractedLiability],
    items: list[_Liability],
    *,
    document: Document,
    content_hash: str,
) -> None:
    valid_types = {"cap", "waiver", "exclusion", "indemnification"}
    for item in items:
        lt = item.limitation_type.strip().lower() if item.limitation_type else "waiver"
        if lt not in valid_types:
            lt = "waiver"
        key = f"{lt}:{_dedupe_key(item.scope)}"
        if not key:
            continue
        if key not in existing:
            existing[key] = ExtractedLiability(
                scope=item.scope.strip(),
                limitation_type=cast(Any, lt),
                description=item.description.strip(),
                extends_beyond_product=item.extends_beyond_product,
                evidence=[],
            )
        else:
            if item.extends_beyond_product:
                existing[key].extends_beyond_product = True
        if item.quote:
            existing[key].evidence.append(_make_evidence(document, content_hash, item.quote))


def _merge_dispute_resolution(
    existing: dict[str, ExtractedDisputeResolution],
    items: list[_DisputeResolution],
    *,
    document: Document,
    content_hash: str,
) -> None:
    valid_mechanisms = {"arbitration", "litigation", "mediation", "other"}
    for item in items:
        mech = item.mechanism.strip().lower() if item.mechanism else "other"
        if mech not in valid_mechanisms:
            mech = "other"
        key = f"{mech}:{_dedupe_key(item.venue or '')}:{_dedupe_key(item.governing_law or '')}"
        if key not in existing:
            existing[key] = ExtractedDisputeResolution(
                mechanism=cast(Any, mech),
                class_action_waiver=item.class_action_waiver,
                jury_trial_waiver=item.jury_trial_waiver,
                venue=item.venue.strip() if item.venue else None,
                governing_law=item.governing_law.strip() if item.governing_law else None,
                description=item.description.strip() if item.description else None,
                evidence=[],
            )
        else:
            if item.class_action_waiver:
                existing[key].class_action_waiver = True
            if item.jury_trial_waiver:
                existing[key].jury_trial_waiver = True
        if item.quote:
            existing[key].evidence.append(_make_evidence(document, content_hash, item.quote))


def _merge_content_ownership(
    existing: dict[str, ExtractedContentOwnership],
    items: list[_ContentOwnership],
    *,
    document: Document,
    content_hash: str,
) -> None:
    valid_types = {
        "license_to_company",
        "user_retains",
        "company_owns",
        "ai_training_rights",
        "likeness_rights",
        "other",
    }
    for item in items:
        ot = item.ownership_type.strip().lower() if item.ownership_type else "other"
        if ot not in valid_types:
            ot = "other"
        key = f"{ot}:{_dedupe_key(item.scope)}"
        if not key:
            continue
        if key not in existing:
            existing[key] = ExtractedContentOwnership(
                ownership_type=cast(Any, ot),
                scope=item.scope.strip(),
                description=item.description.strip(),
                evidence=[],
            )
        if item.quote:
            existing[key].evidence.append(_make_evidence(document, content_hash, item.quote))


def _merge_scope_expansion(
    existing: dict[str, ExtractedScopeExpansion],
    items: list[_ScopeExpansion],
    *,
    document: Document,
    content_hash: str,
) -> None:
    valid_types = {
        "cross_entity",
        "survival_clause",
        "unilateral_modification",
        "binding_heirs",
        "physical_world",
        "other",
    }
    for item in items:
        st = item.scope_type.strip().lower() if item.scope_type else "other"
        if st not in valid_types:
            st = "other"
        key = f"{st}:{_dedupe_key(item.description)}"
        if not key:
            continue
        if key not in existing:
            existing[key] = ExtractedScopeExpansion(
                scope_type=cast(Any, st),
                description=item.description.strip(),
                entities_affected=[e.strip() for e in item.entities_affected],
                evidence=[],
            )
        else:
            for e in item.entities_affected:
                e_norm = e.strip()
                if e_norm and e_norm not in existing[key].entities_affected:
                    existing[key].entities_affected.append(e_norm)
        if item.quote:
            existing[key].evidence.append(_make_evidence(document, content_hash, item.quote))


def _merge_privacy_signals(
    accumulated: PrivacySignals,
    chunk_signals: _PrivacySignals | None,
    *,
    document: Document | None = None,
    content_hash: str = "",
) -> None:
    if not chunk_signals:
        return

    def _add_evidence(quote: str | None) -> None:
        if quote and document:
            accumulated.evidence.append(_make_evidence(document, content_hash, quote))

    def _merge_yes_no(
        current: str | None, new_val: str | None, quote_field: str | None
    ) -> str | None:
        if not new_val:
            return current
        val = new_val.strip().lower()
        if val == "yes":
            _add_evidence(quote_field)
            return "yes"
        elif val == "no" and current in (None, "unclear"):
            _add_evidence(quote_field)
            return "no"
        return current

    accumulated.sells_data = cast(
        Any,
        _merge_yes_no(
            accumulated.sells_data, chunk_signals.sells_data, chunk_signals.sells_data_quote
        ),
    )
    accumulated.cross_site_tracking = cast(
        Any,
        _merge_yes_no(
            accumulated.cross_site_tracking,
            chunk_signals.cross_site_tracking,
            chunk_signals.cross_site_tracking_quote,
        ),
    )
    accumulated.ai_training_on_user_data = cast(
        Any,
        _merge_yes_no(
            accumulated.ai_training_on_user_data,
            chunk_signals.ai_training_on_user_data,
            chunk_signals.ai_training_quote,
        ),
    )
    accumulated.data_minimization = cast(
        Any,
        _merge_yes_no(
            accumulated.data_minimization,
            chunk_signals.data_minimization,
            chunk_signals.data_minimization_quote,
        ),
    )

    if chunk_signals.account_deletion:
        val = chunk_signals.account_deletion.strip().lower()
        if val == "self_service":
            accumulated.account_deletion = "self_service"
            _add_evidence(chunk_signals.account_deletion_quote)
        elif val == "request_required" and accumulated.account_deletion == "not_specified":
            accumulated.account_deletion = "request_required"
            _add_evidence(chunk_signals.account_deletion_quote)

    if chunk_signals.data_retention_summary:
        new_val = chunk_signals.data_retention_summary.strip()
        if not accumulated.data_retention_summary or len(new_val) > len(
            accumulated.data_retention_summary
        ):
            accumulated.data_retention_summary = new_val
            _add_evidence(chunk_signals.data_retention_quote)

    if chunk_signals.consent_model:
        val = chunk_signals.consent_model.strip().lower()
        if val in ("opt_in", "opt_out"):
            if accumulated.consent_model == "not_specified":
                accumulated.consent_model = cast(Any, val)
                _add_evidence(chunk_signals.consent_model_quote)
            elif (
                accumulated.consent_model in ("opt_in", "opt_out")
                and accumulated.consent_model != val
            ):
                accumulated.consent_model = "mixed"
                _add_evidence(chunk_signals.consent_model_quote)
        elif val == "mixed":
            accumulated.consent_model = "mixed"
            _add_evidence(chunk_signals.consent_model_quote)

    if chunk_signals.breach_notification:
        val = chunk_signals.breach_notification.strip().lower()
        if val == "yes":
            accumulated.breach_notification = "yes"
            _add_evidence(chunk_signals.breach_notification_quote)
        elif val == "no" and accumulated.breach_notification == "not_specified":
            accumulated.breach_notification = "no"
            _add_evidence(chunk_signals.breach_notification_quote)

    if chunk_signals.children_data_collection:
        val = chunk_signals.children_data_collection.strip().lower()
        if val == "yes":
            accumulated.children_data_collection = "yes"
            _add_evidence(chunk_signals.children_data_collection_quote)
        elif val == "no" and accumulated.children_data_collection == "not_specified":
            accumulated.children_data_collection = "no"
            _add_evidence(chunk_signals.children_data_collection_quote)


def _clean_raw(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return raw
    for _key, val in raw.items():
        if isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    for k, v in item.items():
                        if v is not None and not isinstance(
                            v, str | bool | int | float | list | dict
                        ):
                            item[k] = str(v)
    return raw


__all__ = [
    "_clean_raw",
    "_dedupe_key",
    "_merge_ai_usage",
    "_merge_children_policy",
    "_merge_content_ownership",
    "_merge_cookie_trackers",
    "_merge_corporate_family",
    "_merge_data_items",
    "_merge_dispute_resolution",
    "_merge_government_access",
    "_merge_international_transfers",
    "_merge_liability",
    "_merge_privacy_signals",
    "_merge_purpose_links",
    "_merge_retention_rules",
    "_merge_scope_expansion",
    "_merge_text_items",
    "_merge_third_parties",
    "_merge_user_rights",
]
