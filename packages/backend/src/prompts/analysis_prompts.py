"""Professional-grade prompt templates for Clausea **batch** analysis (post-crawl pipeline).

Flow:
  1. Extraction   [extraction_service.py]  — structured evidence-backed facts per document
                                             (4 parallel cluster calls, full document chunked).
  2. DOCUMENT_ANALYSIS_PROMPT              — unified deep analysis per document (one call).
  3. PRODUCT_OVERVIEW_PROMPT               — product-level synthesis from core documents only;
                                             output is **cached** and shown on `/products/{slug}`.
                                             This is **not** the same as chat embedding search
                                             (`policy_understanding_prompts` + Pinecone).

Core documents included in product overview:
  privacy_policy, terms_of_service, terms_of_use, terms_and_conditions, cookie_policy,
  gdpr_policy, data_processing_agreement, children_privacy_policy, security_policy.

Excluded from overview (analyzed per-document but not synthesised into the overview):
  community_guidelines, copyright_policy — editorial/moderation and IP; not the primary trust bundle.
"""

# Documents whose analyses are fed into the product overview synthesis.
#
# Only includes types the document classifier actually emits:
#   - terms_of_use / terms_and_conditions are always classified as terms_of_service
#     (the classifier has no separate category for them), so only terms_of_service is listed.
#   - community_guidelines and copyright_policy are excluded: they cover editorial/IP rules,
#     not data/privacy risk, and dilute the overview signal.
#   - security_policy is included: technical/organizational protections matter alongside privacy text.
#   - "other" is excluded by definition (classifier could not assign a type).
OVERVIEW_CORE_DOC_TYPES: frozenset[str] = frozenset(
    {
        "privacy_policy",
        "terms_of_service",
        "cookie_policy",
        "gdpr_policy",
        "data_processing_agreement",
        "children_privacy_policy",
        "security_policy",
    }
)


# ─── 1. DOCUMENT ANALYSIS (deep by default) ────────────────────────────────────

DOCUMENT_ANALYSIS_JSON_SCHEMA = """{
  "summary": string (3-5 concrete sentences),
  "scores": {
    "transparency":          {"score": int 0-10, "justification": string},
    "data_collection_scope": {"score": int 0-10, "justification": string},
    "user_control":          {"score": int 0-10, "justification": string},
    "third_party_sharing":   {"score": int 0-10, "justification": string},
    "data_retention_score":  {"score": int 0-10, "justification": string},
    "security_score":        {"score": int 0-10, "justification": string}
  },
  "liability_risk": int 0-10 | null,
  "compliance_status": {"GDPR": int|null, "CCPA": int|null, "PIPEDA": int|null, "LGPD": int|null} | null,
  "keypoints": [string],
  "applicability": string | null,
  "analysis_completeness": "full" | "partial",
  "coverage_gaps": [string],
  "critical_clauses": [
    {
      "clause_type": string,
      "quote": string,
      "risk_level": "low" | "medium" | "high" | "critical",
      "plain_english": string,
      "why_notable": string
    }
  ],
  "document_risk_breakdown": {
    "risk_by_category": {string: int},
    "top_concerns": [string],
    "positive_protections": [string]
  },
  "key_sections": [
    {
      "section_title": string,
      "content": string,
      "importance": "low" | "medium" | "high" | "critical",
      "analysis": string,
      "related_clauses": [string]
    }
  ]
}
"""

DOCUMENT_ANALYSIS_PROMPT = f"""You are a senior privacy analyst. Produce an evidence-backed analysis of ONE policy document for a privacy-conscious non-lawyer.

## Rules (non-negotiable)
- Use ONLY facts from the extraction below. If absent, state "Not specified in document".
- Every critical clause quote must be an exact substring from the extraction evidence.
- Never output `risk_score` or `verdict` — the platform computes them deterministically from your scores.
- If the extraction is partial, set analysis_completeness to "partial".

## SUMMARY
3-5 concrete sentences. Name exact data types ("precise GPS", "biometric identifiers"), exact recipients ("Meta Pixel", "Google Analytics"), exact rights paths ("Settings > Privacy > Delete"). Start with the service/product name, never with "This document" or "This policy".

## SCORES
Six dimensions, each 0-10 (higher = better for user). Only include a key when the extraction provides real evidence — a missing key is an honest signal.

- **transparency**: clarity of what is collected, why, and by whom. 10=crystal clear, 0=deliberately opaque.
- **data_collection_scope**: breadth of collection. 10=minimal/necessary only, 0=sweeping.
- **user_control**: self-service controls. 10=full opt-out/deletion/portability, 0=none.
- **third_party_sharing**: breadth of sharing. 10=no sharing, 0=unrestricted.
- **data_retention_score**: retention specificity. 10=short specific periods, 0=indefinite. **Omit if extraction has no retention data.**
- **security_score**: stated security measures. 10=E2EE/SOC2/pen-tests, 0=no mention. **Omit if extraction has no security data.**

Calibration: minimal-collection + E2EE → high collection/sharing scores (7-10). Ad-tech ecosystem + AI training on user content → low (0-4). Clear disclosure of invasive practices does NOT raise scores.

## KEYPOINTS
5-10 specific, concrete bullets (fewer acceptable when extraction is thin). Prioritize: AI training on user data, biometrics/health, arbitration waivers, content licenses, government access, cross-entity binding, liability caps.

## CRITICAL CLAUSES
Flag every materially significant clause. For each: clause_type (short label), quote (exact from extraction), risk_level, plain_english (what this means to a non-lawyer), why_notable.

Must flag when present: AI training on user data, biometric/health/genetic collection, forced arbitration, class/jury waivers, perpetual/irrevocable content licenses, cross-entity scope expansion, government access without warrant, international transfers lacking safeguards, unilateral modification rights, user indemnification, liability exclusions.

## DOCUMENT RISK BREAKDOWN
- risk_by_category: one entry per meaningful category (e.g. "data_sharing": 8, "user_control": 3).
- top_concerns: up to 5 substantive concerns. Skip normal category requirements (phone for messaging, email for accounts) unless tied to unusual processing.
- positive_protections: up to 5 genuine protections the document states.

## KEY SECTIONS
3-7 structurally important sections of the document (e.g. "Data Sharing", "User Rights", "Arbitration Clause"). For each: section_title (exact or paraphrased heading), content (verbatim excerpt, max 300 chars), importance (critical/high/medium/low), analysis (one sentence on what this means to the user), related_clauses (list of clause_type values from critical_clauses that this section produced, or empty list).

## APPLICABILITY
One phrase: who/where this applies. Examples: "Global", "EU residents only", "US state residents", "Product-specific: [name]".

## COVERAGE GAPS
What a reasonable user would expect this document type to cover that is absent or vague. Factual, not alarmist.

## COMPLIANCE
Set compliance_status to null when the document has no basis for regulatory scores. When relevant, score only supported regimes 0-10. Use null for individual unsupported keys.

Return valid JSON matching this schema:
{DOCUMENT_ANALYSIS_JSON_SCHEMA}
"""


# ─── 2. PRODUCT OVERVIEW ───────────────────────────────────────────────────────

PRODUCT_OVERVIEW_JSON_SCHEMA = """{
  "summary": string,
  "scores": {
    "transparency":          {"score": int (0-10), "justification": string},
    "data_collection_scope": {"score": int (0-10), "justification": string},
    "user_control":          {"score": int (0-10), "justification": string},
    "third_party_sharing":   {"score": int (0-10), "justification": string}
  },
  "risk_score": int (0-10),
  "verdict": "very_user_friendly" | "user_friendly" | "moderate" | "pervasive" | "very_pervasive",
  "keypoints": [string],
  "data_collected": [string],
  "data_purposes": [string],
  "data_collection_details": [
    {"data_type": string, "purposes": [string]}
  ],
  "third_party_details": [
    {
      "recipient": string,
      "data_shared": [string],
      "purpose": string | null,
      "risk_level": "low" | "medium" | "high"
    }
  ],
  "your_rights": [string],
  "dangers": [string],
  "benefits": [string],
  "recommended_actions": [string],
  "privacy_signals": {
    "sells_data": "yes" | "no" | "unclear",
    "cross_site_tracking": "yes" | "no" | "unclear",
    "account_deletion": "self_service" | "request_required" | "not_specified",
    "data_retention_summary": string | null,
    "consent_model": "opt_in" | "opt_out" | "mixed" | "not_specified",
    "ai_training_on_user_data": "yes" | "no" | "unclear",
    "breach_notification": "yes" | "no" | "not_specified",
    "data_minimization": "yes" | "no" | "unclear",
    "children_data_collection": "yes" | "no" | "not_specified"
  },
  "compliance_status": {"GDPR": int|null, "CCPA": int|null, "PIPEDA": int|null, "LGPD": int|null} | null,
  "contradictions": [
    {
      "document_a": string,
      "document_b": string,
      "description": string,
      "impact": string
    }
  ] | null
}"""

PRODUCT_OVERVIEW_PROMPT = f"""You are a senior policy analyst. Synthesize the full policy bundle into one honest overview.

## Audience and surface
Primary readers are privacy-conscious people. Your job is to help: explain what matters in plain language, what they can control, and where the documents flag real trade-offs.
Be accurate and balanced do not assume malice, pile on negativity, or frame ordinary industry practice as scary.
Regulatory scores in `compliance_status` are secondary signals practical clarity matters more.

## Input
You will receive for each core document:
- document_type and title
- Structured extraction: evidence-backed facts already drawn from the full document
- Per-document analysis: summary, scores, critical clauses, key points, coverage gaps

Core documents may include: privacy policy, terms of service, cookie policy, GDPR/DPA policy, data processing agreement, children's privacy policy, security / trust practices (encryption, audits, incident handling).

## Your task
Produce a comprehensive overview covering data practices and contractual terms together:
- What is collected, why, who receives it, retention, tracking, sale or monetization if stated
- What the user agrees to in terms-of-service style rules: conduct, content licenses, AI use of user material, termination, dispute resolution, liability caps, arbitration
- Rights and controls described in the documents, plus proportionate trade-offs (`dangers`) and genuine positives (`benefits`)
Explicitly surface, when the inputs support it: children's or teens' data, sale / valuable consideration / data brokers, law enforcement or government requests, broad grants (e.g. perpetual content license, training on user data), and safety or high-risk activities if mentioned.

## Non-negotiable rules
- Use ONLY facts from the provided document analyses and extractions.
- Deduplicate across documents report each fact once, clearly.
- When documents conflict, report the conflict in `contradictions` and use the more conservative interpretation for factual claims — not for tone (stay measured, not alarmist).
- If a field cannot be filled from the evidence, use "Not specified in documents" — never invent.
- Be honest: if the company collects a lot of data, do not soften it; but do not invent or exaggerate risks beyond what the documents support.

## SUMMARY
1. Up to 5 sentences: who this company is, what data they collect overall, the most important privacy risk, and the most important protection (if any). Start directly with the company or service name.
2. A markdown bullet list titled "Key Takeaways" - 6-10 specific cross-document findings users must know.

Rules: start with the company/service name; be concrete (exact data types, third parties, exercise paths); use "This means…" or "In practice…" for impact without adding new facts.

## SCORES
Synthesize from all document scores. Where documents conflict, use the most conservative (worst) interpretation for the underlying facts, then assign scores that spread across the 0-10 scale.
Apply the same calibration as single-document analysis: minimal-data / low-sharing / strong technical protections (per extraction) → high scores on `data_collection_scope`, `third_party_sharing`; ad-tech-scale collection, many recipients, tracking, training on user content → low scores on collection and sharing. The product's cached `risk_score` is derived from per-document analyses with privacy_policy weighted most heavily, so privacy-policy scores must honestly reflect breadth of collection and sharing.

Provide only: transparency, data_collection_scope, user_control, third_party_sharing.

## DATA COLLECTED
10-20 specific data types. Be precise: "device fingerprint", "precise GPS coordinates", "browsing history across third-party sites" — not "device information" or "usage data".

## DATA PURPOSES
8-15 specific purposes. Be honest: include "targeted advertising", "sale to data brokers", "AI model training" if present — not just sanitised descriptions.

## DATA COLLECTION DETAILS
For each data type, list the specific purposes for which it is used. Create one entry per data type.

## THIRD PARTY DETAILS
Every named or implied third-party recipient from all documents. For each: what data they receive, for what purpose, and a risk level.

## YOUR RIGHTS
8-12 items: what the documents say users may do (controls, opt-outs, access/deletion paths). Phrase as helpful facts, not lectures. Include how to exercise it — URL, email, in-app path.

## DANGERS
5-7 meaningful risks actually stated in documents. Skip normal category requirements (phone for messaging, email for accounts) unless tied to unusual processing. Include: unusually broad data use, one-sided legal terms, sensitive categories, third-party flows adding real exposure.

## BENEFITS
Up to 8 specific protections the documents actually describe. Balance dangers with genuine positives (encryption, data-sale disclaimers, retention limits).

## RECOMMENDED ACTIONS
Up to 8 practical next steps with exact navigation paths/URLs/contact details.

## PRIVACY SIGNALS
Synthesize from all documents. Use conservative value on conflict.

## COMPLIANCE
Score each regulation 0-10 across all documents. Use null when evidence is insufficient.

## CONTRADICTIONS
List every meaningful inconsistency between documents with verbatim statements and practical impact.

Return valid JSON strictly matching this schema:
{PRODUCT_OVERVIEW_JSON_SCHEMA}
"""


# ─── 3. PRODUCT DEEP ANALYSIS ──────────────────────────────────────────────────

PRODUCT_DEEP_ANALYSIS_JSON_SCHEMA = """{
  "procurement_decision": {
    "decision": "approved" | "conditionally_approved" | "escalate_to_legal" | "do_not_use",
    "overall_risk_rating": "low" | "medium" | "high" | "critical",
    "conditions": [string],
    "executive_brief": string,
    "blocking_issues": [string]
  },
  "data_processing_profile": {
    "controller_processor_classification": "controller" | "processor" | "joint_controller" | "unclear",
    "classification_rationale": string,
    "legal_basis_mapping": [
      {
        "data_category": string,
        "legal_basis": string,
        "adequacy": "adequate" | "questionable" | "missing",
        "note": string | null
      }
    ],
    "subprocessors": [
      {
        "name": string,
        "country": string,
        "data_categories": [string],
        "transfer_mechanism": "adequacy_decision" | "scc" | "bcr" | "unknown" | "not_applicable" | null,
        "risk_note": string | null
      }
    ],
    "data_residency": [string],
    "cross_border_transfers": bool,
    "transfer_mechanisms_noted": [string]
  },
  "article_compliance": {
    "<REGULATION>": {
      "regulation": string,
      "score": int (0-10),
      "status": "Compliant" | "Partially Compliant" | "Non-Compliant" | "Unknown",
      "article_checks": [
        {
          "article": string,
          "requirement": string,
          "status": "met" | "partial" | "missing" | "not_applicable" | "unclear",
          "evidence": string | null,
          "gap": string | null
        }
      ],
      "critical_gaps": [string],
      "strengths": [string],
      "detailed_analysis": string
    }
  },
  "risk_register": [
    {
      "id": string,
      "title": string,
      "description": string,
      "source_document": string,
      "clause_reference": string | null,
      "verbatim_quote": string | null,
      "severity": "critical" | "high" | "medium" | "low",
      "likelihood": "high" | "medium" | "low",
      "regulatory_exposure": [string],
      "blocking": bool,
      "remediation_type": "contractual_negotiation" | "technical_controls" | "user_restriction" | "dpa_required" | "accept_risk" | "reject_vendor" | "policy_update",
      "recommended_action": string,
      "suggested_owner": "Legal" | "DPO" | "IT/Security" | "Procurement" | "HR" | "CISO"
    }
  ],
  "cross_document_analysis": {
    "contradictions": [
      {
        "document_a": string,
        "document_b": string,
        "contradiction_type": string,
        "description": string,
        "document_a_statement": string,
        "document_b_statement": string,
        "impact": string,
        "recommendation": string
      }
    ],
    "information_gaps": [
      {
        "topic": string,
        "severity": "critical" | "high" | "medium" | "low",
        "regulatory_consequence": string | null,
        "recommendation": string | null
      }
    ],
    "document_relationships": [
      {
        "document_a": string,
        "document_b": string,
        "relationship_type": "references" | "supersedes" | "complements" | "conflicts",
        "description": string,
        "evidence": string
      }
    ]
  },
  "contract_clause_review": [
    {
      "clause_type": string,
      "section_reference": string | null,
      "verbatim_quote": string,
      "plain_english": string,
      "standard_assessment": "standard_industry" | "unusual" | "one_sided" | "potentially_unlawful",
      "risk_if_accepted": string,
      "negotiation_lever": string | null,
      "recommended_redline": string | null
    }
  ],
  "workforce_data_assessment": {
    "applicable": bool,
    "risk_level": "low" | "medium" | "high" | "critical" | null,
    "employee_data_categories_mentioned": [string],
    "monitoring_risks": [string],
    "hr_specific_concerns": [string],
    "labor_law_considerations": [string],
    "recommendation": string | null
  },
  "dpia_trigger": {
    "dpia_required": "yes" | "no" | "likely" | "unclear",
    "triggering_factors": [string],
    "recommended_scope": string | null,
    "note": string | null
  },
  "security_posture": {
    "certifications_claimed": [string],
    "encryption_at_rest": "confirmed" | "partial" | "not_mentioned",
    "encryption_in_transit": "confirmed" | "partial" | "not_mentioned",
    "breach_notification_commitment": string | null,
    "breach_notification_timeline": string | null,
    "audit_rights": bool,
    "data_deletion_on_termination": "confirmed" | "unclear" | "not_mentioned",
    "overall_security_assessment": string
  },
  "remediation_roadmap": [
    {
      "priority": "critical" | "high" | "medium" | "low",
      "action": string,
      "rationale": string,
      "suggested_owner": string,
      "timeline": string | null,
      "blocking": bool,
      "related_risk_ids": [string]
    }
  ],
  "business_impact": {
    "for_individuals": {
      "privacy_risk_level": "low" | "medium" | "high" | "critical",
      "data_exposure_summary": string,
      "recommended_actions": [
        {
          "action": string,
          "priority": "critical" | "high" | "medium" | "low",
          "rationale": string,
          "deadline": string | null
        }
      ]
    },
    "for_businesses": {
      "liability_exposure": int (0-10),
      "contract_risk_score": int (0-10),
      "vendor_risk_score": int (0-10),
      "financial_impact": string,
      "reputational_risk": string,
      "operational_risk": string,
      "recommended_actions": [
        {
          "action": string,
          "priority": "critical" | "high" | "medium" | "low",
          "rationale": string,
          "deadline": string | null
        }
      ]
    }
  }
}"""

PRODUCT_DEEP_ANALYSIS_PROMPT = f"""You are a senior privacy counsel and compliance officer conducting a professional vendor due diligence audit. Your output will be used directly by legal teams, DPOs, and procurement to make a go/no-go decision on this platform.

## Input
For each core document you receive: document type, title, full structured extraction (data collected, purposes, third parties, legal bases, rights, AI usage, privacy signals), and per-document analysis (summary, scores, critical clauses, key points, coverage gaps).

## Your task

### 1. PROCUREMENT DECISION
Give a clear, defensible recommendation.
- `decision`: "approved" (low risk, use freely), "conditionally_approved" (usable with listed mitigations), "escalate_to_legal" (material issues requiring legal negotiation), "do_not_use" (blocking issues not resolvable without vendor changes).
- `overall_risk_rating`: single aggregate risk level.
- `conditions`: specific, measurable mitigations that must be in place before or during use (e.g. "Execute DPA before processing any personal data", "Limit to anonymized data only").
- `executive_brief`: 2-3 sentences for the CISO or Head of Legal — what this platform does with data and the single most important concern.
- `blocking_issues`: issues that prevent any use until resolved. Empty if decision is "approved".

### 2. DATA PROCESSING PROFILE
Classify the vendor relationship and map data flows.
- `controller_processor_classification`: Is the vendor acting as a data processor (on your behalf), controller (independently decides purpose/means), joint controller, or unclear?
- `classification_rationale`: what in the documents supports the classification.
- `legal_basis_mapping`: For every distinct data category processed, state the legal basis claimed and whether it is adequate, questionable (e.g. legitimate interest for marketing), or missing.
- `subprocessors`: All named or strongly implied subprocessors. Include country, data categories they touch, and the transfer mechanism (SCC, adequacy decision, BCR, unknown). Flag "unknown" where transfer mechanism is not stated.
- `data_residency`: Countries/regions where data is stored or processed.
- `cross_border_transfers`: true if data leaves the user's home jurisdiction.
- `transfer_mechanisms_noted`: Transfer mechanisms explicitly stated in the documents.

### 3. ARTICLE-LEVEL COMPLIANCE
For each regulation in scope (GDPR if EU users are mentioned; CCPA if California/US users; include PIPEDA, LGPD where relevant), produce a per-article checklist.
Only include regulations actually in scope — do not fabricate regulation checks for jurisdictions the documents don't address.

For GDPR, check at minimum: Art. 5 (principles), Art. 6 (legal basis), Art. 13/14 (transparency), Art. 15 (access), Art. 17 (erasure), Art. 20 (portability), Art. 22 (automated decisions), Art. 25 (privacy by design), Art. 28 (processor requirements / DPA), Art. 32 (security), Art. 33/34 (breach notification), Art. 44-49 (international transfers).
For each article check: status is "met" (clearly addressed), "partial" (addressed but incomplete), "missing" (required but absent), "not_applicable" (genuinely out of scope), "unclear" (ambiguous).
Include `evidence` (quote or clause reference) for "met" and "partial". Include `gap` for "missing" and "partial".
`score` 0-10 and `detailed_analysis` paragraph (4-6 sentences) covering overall posture, critical gaps, and recommended priority.

### 4. RISK REGISTER
Produce a structured register of all material risks identified across all documents. This is the core deliverable — it must be actionable, not generic.

For each risk item:
- Assign a sequential `id` (e.g. "R001", "R002").
- `title`: short, specific (cite the practice or clause type).
- `description`: what the risk is and why it matters.
- `source_document`: document type where the risk appears.
- `clause_reference`: section or clause number if stated.
- `verbatim_quote`: exact text supporting the finding (max 300 chars).
- `severity`: impact if the risk materializes. `likelihood`: probability of materializing.
- `regulatory_exposure`: specific articles or regulations at risk (e.g. "GDPR Art. 17", "CCPA §1798.105").
- `blocking`: true if this prevents deployment until resolved.
- `remediation_type`: the primary mitigation approach.
- `recommended_action`: concrete next step (e.g. "Require DPA with explicit Art. 28 clauses before processing any EU personal data").
- `suggested_owner`: team accountable for the remediation.

Minimum: 5 risk items. Maximum: 20. Omit minor or standard-industry items below the threshold of materiality.

### 5. CROSS-DOCUMENT ANALYSIS
- `contradictions`: Only where two documents make genuinely conflicting statements. Include verbatim statements from both documents. Never flag silence as contradiction.
- `information_gaps`: Policy areas a compliance team would expect to be addressed that are absent across all documents. For each: severity, the regulatory consequence of the gap, and a recommendation.
- `document_relationships`: How documents reference, supersede, or complement each other. Cite specific text as `evidence`.

### 6. CONTRACT CLAUSE REVIEW
Flag up to 10 clauses that legal counsel or procurement should review before signing. Focus on: broad content/data licenses, unilateral change rights, indemnification, limitation of liability, arbitration/class-action waivers, auto-renewal, and data handling on termination.
For each:
- `standard_assessment`: "standard_industry" (normal for this type of agreement), "unusual" (not typical but not necessarily problematic), "one_sided" (materially favors the vendor), "potentially_unlawful" (may conflict with applicable law).
- `risk_if_accepted`: concrete harm if the clause is accepted as-is.
- `negotiation_lever`: guidance for enterprise agreement negotiation (e.g. "Enterprise agreements typically allow carve-out of AI training on customer data").
- `recommended_redline`: suggested alternative language or deletion.

### 7. WORKFORCE DATA ASSESSMENT
Assess whether using this platform for employee personal data creates specific risks.
- `applicable`: true if the platform could plausibly be used to process employee data (productivity tools, communication platforms, HR systems, analytics tools used in workplace contexts — default true for general-purpose B2B platforms).
- If applicable: identify monitoring risks (keystroke logging, productivity tracking, location), HR-specific concerns (profiling, automated decisions affecting employment), and labor law considerations (Works Council requirements in EU, employee consent limitations, NLRA implications in the US, TUPE / employment law on termination).
- `recommendation`: one concrete sentence on whether to proceed and under what controls.

### 8. DPIA TRIGGER ASSESSMENT
Assess whether a Data Protection Impact Assessment is required under GDPR Art. 35 or equivalent.
Triggering factors include: large-scale processing of sensitive data, systematic monitoring of employees or public spaces, use of new technologies with high risk, automated decision-making with significant effects, processing of children's data.
If `dpia_required` is "yes" or "likely", provide a `recommended_scope` paragraph.

### 9. SECURITY POSTURE
Summarise the vendor's described security practices. Do NOT invent certifications or claims.
- `certifications_claimed`: exactly what the documents state (e.g. "ISO 27001 certified", "SOC 2 Type II").
- Encryption claims, breach notification timeline (flag if >72 hours or unspecified — GDPR requires 72h to authority).
- `audit_rights`: true only if the documents explicitly grant customers the right to audit or receive audit reports.
- `data_deletion_on_termination`: whether the documents commit to deleting or returning data on contract end.
- `overall_security_assessment`: 2-3 sentences on the overall security posture based solely on the documents.

### 10. REMEDIATION ROADMAP
Produce a prioritized action plan synthesising the risk register and compliance gaps. Each item should reference the relevant risk IDs.
- `timeline`: "Before any deployment", "Before processing EU personal data", "Within 30 days", "Within 90 days", "Ongoing".
- `blocking`: true if no data processing should begin until this is resolved.
- Order items by priority (critical → low).

### 11. BUSINESS IMPACT
For individuals: privacy risk level, what data exposure means in practice, specific actions they can take.
For businesses: score liability, contract risk, and vendor risk. Describe financial, reputational, and operational risk concretely — not as generic statements.

## Non-negotiable rules
- Evidence only. Cite source document type for every finding.
- Do NOT invent compliance violations, subprocessors, or certification claims not stated in the documents.
- Do NOT conflate absence of mention with a violation — mark it "missing" in compliance checks, not "non_compliant".
- Scope: a risk in a global policy ranks higher than the same risk in a product-specific policy.
- Contradictions require active conflict, not just different scopes.

Return valid JSON strictly matching this schema:
{PRODUCT_DEEP_ANALYSIS_JSON_SCHEMA}
"""
