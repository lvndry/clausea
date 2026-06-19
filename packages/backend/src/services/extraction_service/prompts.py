"""Extraction prompts and cluster specification builders."""

import json
from typing import Any

from src.models.document import Document

EXTRACTION_SYSTEM_PROMPT = """You are an expert legal-document information extractor.

Your job is to extract structured facts ONLY from the provided text chunk.

Critical rules:
- Only extract items explicitly present in the text chunk.
- For every extracted item, provide an evidence quote that is an EXACT substring of the provided chunk.
- If a field is not present, return an empty list for that field.
- Do not paraphrase evidence quotes; copy exact text.
"""

_CLUSTER_SPECS: dict[str, tuple[dict[str, Any], str]] = {}


def _build_cluster_specs() -> None:
    _CLUSTER_SPECS["data_practices"] = (
        {
            "data_collected": [
                {
                    "data_type": "Email address",
                    "sensitivity": "low | medium | high | sensitive",
                    "required": "required | optional | unclear",
                    "quote": "exact quote",
                }
            ],
            "data_purposes": [
                {
                    "data_type": "Email address",
                    "purposes": ["Account creation", "Marketing"],
                    "legal_basis": "consent | legitimate_interest | contract | null",
                    "quote": "exact quote",
                }
            ],
            "retention_policies": [
                {
                    "data_scope": "Account data",
                    "duration": "30 days after deletion",
                    "conditions": "After account closure or null",
                    "quote": "exact quote",
                }
            ],
            "security_measures": [
                {"value": "Encryption in transit and at rest", "quote": "exact quote"}
            ],
            "cookies_and_trackers": [
                {
                    "name_or_type": "Google Analytics",
                    "category": "essential | analytics | advertising | social | other",
                    "duration": "2 years or null",
                    "third_party": True,
                    "opt_out_mechanism": "Browser settings or null",
                    "quote": "exact quote",
                }
            ],
        },
        (
            "Extract ALL of the following from this chunk:\n"
            "1. DATA COLLECTED: every data type mentioned (email, IP, location, biometric, health, financial, etc.).\n"
            "   Classify sensitivity: low (public info), medium (PII), high (financial/precise location), sensitive (biometric/health/genetic/racial/religious).\n"
            "   Note whether required or optional for the service.\n"
            "2. DATA PURPOSES: link each data type to its purposes. Include legal basis if stated (consent, legitimate interest, contract).\n"
            "3. RETENTION: specific durations, conditions, deletion timelines per data scope.\n"
            "4. SECURITY: encryption, access controls, audits, certifications, breach response.\n"
            "5. COOKIES & TRACKERS: specific cookies, pixels, SDKs, fingerprinting. Include category, duration, whether third-party, and opt-out mechanism if stated."
        ),
    )

    _CLUSTER_SPECS["sharing_transfers"] = (
        {
            "third_party_details": [
                {
                    "recipient": "Advertisers",
                    "data_shared": ["email", "location data"],
                    "purpose": "Targeted advertising",
                    "risk_level": "low | medium | high",
                    "quote": "exact quote",
                }
            ],
            "international_transfers": [
                {
                    "destination": "United States",
                    "mechanism": "SCC|adequacy_decision|consent|null",
                    "data_types": ["email", "usage data"],
                    "quote": "exact quote",
                }
            ],
            "government_access": [
                {
                    "authority_type": "Law enforcement",
                    "conditions": "Valid court order or subpoena",
                    "data_scope": "str|null",
                    "quote": "exact quote",
                }
            ],
            "corporate_family_sharing": [
                {
                    "entities": ["Meta Platforms", "Instagram", "WhatsApp"],
                    "data_shared": ["account info", "usage data"],
                    "purpose": "Cross-platform analytics",
                    "quote": "exact quote",
                }
            ],
        },
        (
            "Extract ALL of the following from this chunk:\n"
            "1. THIRD-PARTY SHARING: who receives data, what data, why, risk level (low/medium/high).\n"
            "   Include service providers, advertisers, analytics partners, business partners.\n"
            "2. INTERNATIONAL TRANSFERS: where data flows geographically. Include the legal transfer mechanism if stated\n"
            "   (Standard Contractual Clauses, adequacy decisions, binding corporate rules, user consent).\n"
            "3. GOVERNMENT / LAW ENFORCEMENT ACCESS: under what conditions data is shared with authorities.\n"
            "   Include the legal standard required (court order, subpoena, national security letter, voluntary).\n"
            "4. CORPORATE FAMILY SHARING: data shared with parent companies, subsidiaries, affiliates.\n"
            "   Name specific entities when mentioned. Note if agreeing to one service shares data with the whole corporate group."
        ),
    )

    _CLUSTER_SPECS["rights_ai"] = (
        {
            "user_rights": [
                {
                    "right_type": "Deletion",
                    "description": "Delete your account and associated data",
                    "mechanism": "Settings > Privacy > Delete Account, or email privacy@example.com",
                    "quote": "exact quote",
                }
            ],
            "consent_mechanisms": [
                {
                    "value": "Opt-out of marketing emails via unsubscribe link",
                    "quote": "exact quote",
                }
            ],
            "account_lifecycle": [
                {"value": "Data deleted 30 days after account closure", "quote": "exact quote"}
            ],
            "ai_usage": [
                {
                    "usage_type": "training_on_user_data | automated_decisions | profiling | content_generation | recommendation | moderation | other",
                    "description": "User content used to train language models",
                    "data_involved": ["text messages", "uploaded files"],
                    "opt_out_available": "yes | no | unclear",
                    "opt_out_mechanism": "Settings > Privacy > AI Training or null",
                    "consequences": "AI features may be less personalized or null",
                    "quote": "exact quote",
                }
            ],
            "children_policy": {
                "minimum_age": 13,
                "parental_consent_required": True,
                "special_protections": "Limited data collection for under-16s or null",
                "quote": "exact quote or null",
            },
            "privacy_signals": {
                "sells_data": "yes|no|unclear|null",
                "sells_data_quote": "str|null",
                "cross_site_tracking": "yes|no|unclear|null",
                "cross_site_tracking_quote": "str|null",
                "account_deletion": "self_service|request_required|not_specified|null",
                "account_deletion_quote": "str|null",
                "data_retention_summary": "str|null",
                "data_retention_quote": "str|null",
                "consent_model": "opt_in|opt_out|mixed|not_specified|null",
                "consent_model_quote": "str|null",
                "ai_training_on_user_data": "yes|no|unclear|null",
                "ai_training_quote": "str|null",
                "breach_notification": "yes|no|not_specified|null",
                "breach_notification_quote": "str|null",
                "data_minimization": "yes|no|unclear|null",
                "data_minimization_quote": "str|null",
                "children_data_collection": "yes|no|not_specified|null",
                "children_data_collection_quote": "str|null",
            },
        },
        (
            "Extract ALL of the following from this chunk:\n"
            "1. USER RIGHTS: access, correction, deletion, portability, objection, restriction, withdrawal of consent.\n"
            "   Include the MECHANISM (URL, settings path, email address) to exercise each right.\n"
            "2. CONSENT MECHANISMS: how consent is obtained, withdrawn, managed. Granularity of choices.\n"
            "3. ACCOUNT LIFECYCLE: what happens to data on account closure/deletion/inactivity.\n"
            "   Include data portability/export options, deletion timelines, what survives deletion.\n"
            "4. AI / PROFILING / AUTOMATED DECISIONS:\n"
            "   - Is user data/content used to TRAIN AI models? Can users opt out?\n"
            "   - Are automated decisions made about users (content moderation, pricing, eligibility)?\n"
            "   - Is profiling performed? What profiles are built and for what purpose?\n"
            "   - Are AI-generated outputs based on user data (voice cloning, style mimicking)?\n"
            "5. CHILDREN & AGE: minimum age, COPPA/children's privacy, parental consent, special protections for minors.\n"
            "6. PRIVACY SIGNALS: only set a field if the chunk EXPLICITLY mentions it, null otherwise."
        ),
    )

    _CLUSTER_SPECS["legal_scope"] = (
        {
            "liability": [
                {
                    "scope": "Service use and all affiliated properties",
                    "limitation_type": "cap | waiver | exclusion | indemnification",
                    "description": "Liability limited to fees paid in last 12 months",
                    "extends_beyond_product": False,
                    "quote": "exact quote",
                }
            ],
            "dispute_resolution": [
                {
                    "mechanism": "arbitration | litigation | mediation | other",
                    "class_action_waiver": True,
                    "jury_trial_waiver": True,
                    "venue": "Delaware or null",
                    "governing_law": "State of California or null",
                    "description": "Binding arbitration with opt-out window or null",
                    "quote": "exact quote",
                }
            ],
            "content_ownership": [
                {
                    "ownership_type": "license_to_company | user_retains | company_owns | ai_training_rights | likeness_rights | other",
                    "scope": "Perpetual, irrevocable, worldwide, sublicensable license",
                    "description": "Company may use uploaded content to train AI models and create derivative works",
                    "quote": "exact quote",
                }
            ],
            "scope_expansion": [
                {
                    "scope_type": "cross_entity | survival_clause | unilateral_modification | binding_heirs | physical_world | other",
                    "description": "Terms apply to all subsidiaries including theme parks and retail stores",
                    "entities_affected": ["Disney+", "Disneyland", "ESPN"],
                    "quote": "exact quote",
                }
            ],
            "indemnification": [
                {
                    "value": "User indemnifies company against all claims from user content",
                    "quote": "exact quote",
                }
            ],
            "termination_consequences": [
                {
                    "value": "Company may delete all content 30 days after termination",
                    "quote": "exact quote",
                }
            ],
            "dangers": [
                {
                    "value": "No cap on liability for user-generated content claims",
                    "quote": "exact quote",
                }
            ],
            "benefits": [
                {"value": "30-day opt-out window for arbitration clause", "quote": "exact quote"}
            ],
            "recommended_actions": [
                {
                    "value": "Send opt-out notice to arbitration@example.com within 30 days",
                    "quote": "exact quote",
                }
            ],
        },
        (
            "Extract ALL of the following from this chunk:\n"
            "1. LIABILITY: limitations, caps, waivers, exclusions.\n"
            "   CRITICAL: flag if liability waivers EXTEND BEYOND the digital product — e.g. waiving\n"
            "   liability for physical injury at venues, medical claims, or unrelated subsidiary services.\n"
            "   Set extends_beyond_product=true for these.\n"
            "2. DISPUTE RESOLUTION: arbitration clauses, class action waivers, jury trial waivers,\n"
            "   venue/forum requirements, mass arbitration rules, opt-out windows.\n"
            "   Include governing law/jurisdiction.\n"
            "3. CONTENT OWNERSHIP / IP: what rights the company claims over user content.\n"
            "   Flag perpetual/irrevocable/sublicensable licenses, AI training rights over user content,\n"
            "   rights to user's likeness/voice/image, and derivative work rights.\n"
            "4. SCOPE EXPANSION: clauses extending reach beyond what users expect.\n"
            "   - cross_entity: agreeing to one service binds you to terms of subsidiaries/affiliates.\n"
            "   - survival_clause: obligations surviving termination.\n"
            "   - unilateral_modification: company can change terms without explicit consent.\n"
            "   - binding_heirs: terms binding user's estate or heirs.\n"
            "   - physical_world: digital terms affecting physical-world rights (medical, biometric, property).\n"
            "5. INDEMNIFICATION: what the user is personally liable for.\n"
            "6. TERMINATION CONSEQUENCES: what happens to data, content, and access on termination.\n"
            "7. DANGERS: material risks, one-sided legal terms, or meaningful trade-offs **stated in the chunk**.\n"
            "   Skip routine signup or category-norm requirements (e.g. phone for messaging, email for accounts)\n"
            "   unless the text ties them to unusual extra processing, sharing, or retention worth flagging.\n"
            "   Goal: help users prioritize — not list every basic requirement as a red flag.\n"
            "8. BENEFITS: protections and user-friendly practices the document actually claims.\n"
            "9. RECOMMENDED ACTIONS: practical steps a user can take (settings, reading linked policies, opt-outs)\n"
            "   with specific URLs or instructions when present — helpful tone, not alarmist."
        ),
    )


_build_cluster_specs()

CLUSTER_NAMES = ["data_practices", "sharing_transfers", "rights_ai", "legal_scope"]


def _get_extraction_prompt(document: Document, chunk: str, cluster: str) -> str:
    schema_hint, notes = _CLUSTER_SPECS[cluster]

    header = f"""\
Extract evidence-backed facts from this policy document chunk.

Document URL: {document.url}
Document Type: {document.doc_type}

Text chunk:
{chunk}

Return a JSON object with ONLY the keys listed below (all keys required).
Evidence quotes must be EXACT substrings of the chunk above.
"""
    return f"{header}\n{json.dumps(schema_hint, separators=(',', ':'))}\n\nNotes:\n{notes}"


__all__ = [
    "CLUSTER_NAMES",
    "EXTRACTION_SYSTEM_PROMPT",
    "_CLUSTER_SPECS",
    "_build_cluster_specs",
    "_get_extraction_prompt",
]
