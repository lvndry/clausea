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
  gdpr_policy, data_processing_agreement, children_privacy_policy.

Excluded from overview (analyzed per-document but not synthesised into the overview):
  community_guidelines, copyright_policy — these address editorial/IP rules, not data/privacy risk.
"""

# Documents whose analyses are fed into the product overview synthesis.
#
# Only includes types the document classifier actually emits:
#   - terms_of_use / terms_and_conditions are always classified as terms_of_service
#     (the classifier has no separate category for them), so only terms_of_service is listed.
#   - community_guidelines and copyright_policy are excluded: they cover editorial/IP rules,
#     not data-privacy risk, and dilute the overview signal.
#   - "other" and "unclassified" are excluded by definition.
OVERVIEW_CORE_DOC_TYPES: frozenset[str] = frozenset(
    {
        "privacy_policy",
        "terms_of_service",
        "cookie_policy",
        "gdpr_policy",
        "data_processing_agreement",
        "children_privacy_policy",
    }
)


# ─── 1. DOCUMENT ANALYSIS (deep by default) ────────────────────────────────────

DOCUMENT_ANALYSIS_JSON_SCHEMA = """{
  "summary": string,
  "scores": {
    "transparency":          {"score": int (0-10), "justification": string},
    "data_collection_scope": {"score": int (0-10), "justification": string},
    "user_control":          {"score": int (0-10), "justification": string},
    "third_party_sharing":   {"score": int (0-10), "justification": string},
    "data_retention_score":  {"score": int (0-10), "justification": string},
    "security_score":        {"score": int (0-10), "justification": string}
  },
  "risk_score": int (0-10),
  "verdict": "very_user_friendly" | "user_friendly" | "moderate" | "pervasive" | "very_pervasive",
  "liability_risk": int (0-10) | null,
  "compliance_status": {"GDPR": int|null, "CCPA": int|null, "PIPEDA": int|null, "LGPD": int|null} | null,
  "keypoints": [string],
  "applicability": string | null,
  "analysis_completeness": "full" | "partial",
  "coverage_gaps": [string],
  "critical_clauses": [
    {
      "clause_type": "data_collection" | "data_sharing" | "user_rights" | "liability"
                   | "indemnification" | "retention" | "deletion" | "security"
                   | "breach_notification" | "dispute_resolution" | "governing_law",
      "section_title": string | null,
      "quote": string,
      "risk_level": "low" | "medium" | "high" | "critical",
      "plain_english": string,
      "why_notable": string,
      "compliance_impact": [string]
    }
  ],
  "document_risk_breakdown": {
    "overall_risk": int (0-10),
    "risk_by_category": {string: int},
    "top_concerns": [string],
    "positive_protections": [string],
    "missing_information": [string],
    "applicability": string | null
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
}"""

DOCUMENT_ANALYSIS_PROMPT = f"""You are a senior privacy and legal analyst at a policy intelligence firm. Produce a thorough, evidence-backed analysis of a single policy document that a non-lawyer can trust and act on.

## Input
You will receive:
1. Document metadata — title, type, URL, locale, regions.
2. Structured extraction — evidence-backed facts drawn from the document by a prior extraction step.
3. A completeness indicator — whether the extraction covered the full document or was truncated.

## Non-negotiable rules
- Use ONLY facts present in the extraction input.
- Every critical clause must use the exact quote from the extraction evidence.
- If something is absent from the extraction, state "Not specified in document" — never infer or fabricate.
- If the extraction is partial, set analysis_completeness to "partial" and list what is unknown in coverage_gaps.

---

## SUMMARY
Write for a user who knows nothing about law. This is the first thing they will read.

Structure:
1. Two or three direct sentences: what service is this, the single biggest data concern OR strongest protection, and what the user must know immediately. Start directly with the company or service name.
2. A markdown bullet list titled "**Highlights & Main Points**" — 5–8 specific findings.

Rules:
- Never start with "This document", "The policy", or "This service".
- Be concrete: name exact data types ("precise GPS location", "browsing history across sites", "biometric identifiers"), exact recipients ("Meta Pixel", "Google Analytics", "Salesforce"), exact rights ("delete account via Settings > Privacy > Delete Account").
- Use "This means…" or "In practice…" to explain user impact — without adding new facts not in the extraction.
- No legalese, no hedging, no marketing language.

---

## CRITICAL CLAUSES
Identify every clause in the extraction that is materially significant for the user's privacy, rights, or legal exposure.

For each clause:
- clause_type: pick the closest match.
- quote: exact text from the document — taken directly from the extraction's evidence fields.
- section_title: section heading from the document if available, else null.
- risk_level: low / medium / high / critical.
- plain_english: what this means to a non-lawyer, one or two sentences.
- why_notable: why this clause matters — surprising scope, invasive practice, strong protection, or significant legal weight.
- compliance_impact: regulations directly implicated.

Always produce a clause entry for any of the following if present in the extraction:
- AI training on user-generated content or data
- Biometric, health, genetic, or precise location data collection
- Forced arbitration and class-action / jury-trial waivers
- Broad content licenses (perpetual, irrevocable, sublicensable, for AI or commercial use)
- Cross-entity or subsidiary scope expansion ("by using this service you agree to our affiliates' terms")
- Government and law enforcement data access — especially without a warrant requirement
- International data transfers without adequate safeguards
- Unilateral right to modify terms with minimal or no notice
- User indemnification obligations
- Liability caps or exclusions that expose the user

---

## SCORES (integers 0–10, higher = better for the user)
- transparency: Does the document clearly explain what data is collected, why, and by whom? 10 = very clear, 0 = deliberately opaque.
- data_collection_scope: How limited is data collection? 10 = minimal/necessary only, 0 = sweeping collection of everything possible.
- user_control: How much control does the user have? 10 = full opt-out, deletion, portability with self-service. 0 = no control at all.
- third_party_sharing: How limited is data sharing? 10 = no third-party sharing. 0 = unrestricted sharing with all partners.
- data_retention_score: How limited is retention duration? 10 = short, specific periods. 0 = indefinite. If not stated → score 5, justification "Not specified in document".
- security_score: Quality of stated security measures. 10 = strong, specific technical controls. 0 = no mention. If not stated → score 5, justification "Not specified in document".

---

## RISK SCORE
Compute: risk_score = round(10 - (transparency×0.20 + data_collection_scope×0.25 + user_control×0.25 + third_party_sharing×0.30)).
Clamp to [0, 10].

## VERDICT
Map risk_score: 0–2 → very_user_friendly, 3–4 → user_friendly, 5–6 → moderate, 7–8 → pervasive, 9–10 → very_pervasive.

---

## KEY POINTS (`keypoints`)
Include this array on **every** document analysis: 5–10 user-facing takeaways when `analysis_completeness` is `full`; fewer (but at least one) when `partial` and the extraction is thin. Concrete and specific; no generalisations.
Prioritise: AI training, biometrics, arbitration, scope expansion, content licenses, government access, cross-entity binding.

---

## APPLICABILITY (`applicability`)
One short phrase: **who and where this document applies** (jurisdiction, product, or audience). **Do not** use this field for how *much* data is collected — that is the score `data_collection_scope`.

Examples: "Global", "EU-specific", "US state residents only", "Product-specific: [name]", "Service-specific: [name]". Use document title, URL, locale, and regions.

Duplicate the **same string** inside `document_risk_breakdown.applicability`.

---

## COVERAGE GAPS
List things a user would reasonably expect a document of this type to cover that are absent or deliberately vague.
Examples: "No breach notification timeline stated", "Retention periods not specified for any data category", "Security measures not described", "No information on how to exercise deletion rights".
This is factual reporting — a gap does not mean non-compliance.

---

## COMPLIANCE (`compliance_status`)
Not every document should carry regulatory scores.

- Set **`compliance_status` to `null` (omit the object)** when the document has **no honest basis** for these regimes: e.g. pure liability/dispute ToS with no personal-data content, a narrow cookie *mechanics* notice with no rights narrative, boilerplate unrelated to data protection, or extraction so thin that no regime can be scored without guessing.
- When the document **does** address privacy, data subjects, rights, regions, or legal bases, include the object and score **only** regimes supported by the extraction.
- **Per-regulation `null`**: inside the object, use `null` for a given key when that specific law is not implicated or evidence is insufficient. If every key would be `null`, set the whole **`compliance_status` to `null`** instead of an empty object.
- Scores are 0–10 (higher = stronger alignment with what that regime typically expects to see disclosed); do not invent scores to fill all four keys.

---

## DOCUMENT RISK BREAKDOWN
- overall_risk: same value as risk_score.
- risk_by_category: one entry per meaningful category found in the extraction (e.g. "data_sharing": 8, "retention": 5).
- top_concerns: up to 5 specific concerns with concrete detail.
- positive_protections: up to 5 specific protective measures actually stated in the document.
- missing_information: same list as coverage_gaps.
- applicability: same value as the top-level `applicability` field.

---

## KEY SECTIONS
3–7 most important sections with:
- section_title: as it appears in the document.
- content: full text of the section (from extraction).
- importance: low / medium / high / critical.
- analysis: plain-language explanation of the section's significance.
- related_clauses: indices (as strings) of any critical_clauses entries that originate from this section.

---

Return valid JSON strictly matching this schema:
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

PRODUCT_OVERVIEW_PROMPT = f"""You are a senior policy analyst. Synthesize the full **core** policy bundle into one honest overview.

## Audience and surface
Primary readers are **privacy-aware users**, not compliance officers. Your JSON is **cached after crawl** and shown on Clausea's product page so people can understand what they are signing up for **before** reading raw documents. Lead with clarity and user impact. Regulatory scores in `compliance_status` are secondary signals — plain-language risks and rights matter more.

## Input
You will receive for each core document:
- document_type and title
- Structured extraction: evidence-backed facts already drawn from the full document
- Per-document analysis: summary, scores, critical clauses, key points, coverage gaps

Core documents may include: privacy policy, terms of service / terms of use / terms and conditions, cookie policy, GDPR/DPA policy, data processing agreement, children's privacy policy.

## Your task
Produce a comprehensive overview covering **data practices and contractual terms together**:
- What is collected, why, who receives it, retention, tracking, sale or monetization if stated
- What the user **agrees to** in terms-of-service style rules: conduct, content licenses, AI use of user material, termination, dispute resolution, liability caps, arbitration
- Rights and controls described in the documents, plus concrete dangers and benefits
Explicitly surface, when the inputs support it: **children's or teens' data**, **sale / valuable consideration / data brokers**, **law enforcement or government requests**, **broad grants** (e.g. perpetual content license, training on user data), and **safety or high-risk activities** if mentioned.

## Non-negotiable rules
- Use ONLY facts from the provided document analyses and extractions.
- Deduplicate across documents — report each fact once, clearly.
- When documents conflict, report the conflict in `contradictions` and use the more conservative interpretation.
- If a field cannot be filled from the evidence, use "Not specified in documents" — never invent.
- Be honest: if the company collects a lot of data, do not soften it.

---

## SUMMARY
1. Three or four direct sentences: who this company is, what data they collect overall, the most important privacy risk, and the most important protection (if any). Start directly with the company or service name.
2. A markdown bullet list titled "**Key Takeaways**" — 6–10 specific cross-document findings users must know.

Rules:
- Never start with "We analyzed", "Based on the documents", or "Across all documents".
- Be concrete: exact data types, exact third parties, exact rights with how to exercise them.
- Use "This means…" or "In practice…" to explain impact — without adding facts not in the input.

---

## SCORES
Synthesize from all document scores. Where documents conflict, use the most conservative (worst) interpretation.
Provide only: transparency, data_collection_scope, user_control, third_party_sharing.

---

## DATA COLLECTED
10–20 specific data types. Be precise: "device fingerprint", "precise GPS coordinates", "browsing history across third-party sites", "keystroke dynamics" — not "device information" or "usage data".

---

## DATA PURPOSES
8–15 specific purposes. Be honest: include "targeted advertising", "sale to data brokers", "AI model training" if present — not just sanitised descriptions.

---

## DATA COLLECTION DETAILS
For each data type, list the specific purposes for which it is used. Create one entry per data type.

---

## THIRD PARTY DETAILS
Every named or implied third-party recipient from all documents. For each: what data they receive, for what purpose, and a risk level.

---

## YOUR RIGHTS
8–12 specific user rights. For each: exactly how to exercise it — URL, email, in-app path, or process name if stated in the documents.
Examples:
- "Delete your account and data — go to Settings > Privacy > Delete Account or email privacy@company.com"
- "Opt out of AI training on your content — toggle off in Settings > Data > AI Personalization"
- "Request a copy of your data — submit a DSAR at company.com/privacy/request"

---

## DANGERS
5–7 specific, concrete risks actually stated in the documents. Not generic observations.
Each entry should reference what is actually said and explain the real-world impact.
Examples:
- "Photos and videos you upload may be used to train AI models with no opt-out available (Privacy Policy §4.3)"
- "Agreeing to the Terms binds you to mandatory arbitration, eliminating your right to sue in court"
- "Location data is shared with 37 advertising partners even when the app is running in the background"

---

## BENEFITS
5–7 specific positive practices actually found in the documents. Do not invent or inflate.
Examples:
- "End-to-end encryption for all messages, meaning the company cannot read them"
- "Transparent list of data broker partners published at company.com/partners"

---

## RECOMMENDED ACTIONS
5–8 specific, immediately actionable steps. Include exact navigation paths, URLs, or contact details when available in the documents.
Example: "Review and tighten your ad personalisation settings — Settings > Ads > Manage Preferences"

---

## PRIVACY SIGNALS
Synthesize from all documents. When documents conflict, use the more conservative value.

---

## COMPLIANCE
Score each regulation 0–10 across all documents combined. Use null when evidence is insufficient.

---

## CONTRADICTIONS
List every meaningful inconsistency between documents. This is valuable information — users and compliance teams need it.
Example: "Privacy Policy states data is not sold to third parties; Terms of Service permits sharing with 'commercial partners for business purposes' — these statements may conflict on whether revenue-generating data transfers constitute a sale."

---

Return valid JSON strictly matching this schema:
{PRODUCT_OVERVIEW_JSON_SCHEMA}
"""


# ─── 3. PRODUCT DEEP ANALYSIS ──────────────────────────────────────────────────

PRODUCT_DEEP_ANALYSIS_JSON_SCHEMA = """{
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
    "information_gaps": [string],
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
  "enhanced_compliance": {
    "<REGULATION>": {
      "regulation": string,
      "score": int (0-10),
      "status": "Compliant" | "Partially Compliant" | "Non-Compliant" | "Unknown",
      "strengths": [string],
      "gaps": [string],
      "violations": [
        {
          "requirement": string,
          "violation_type": "missing" | "unclear" | "non_compliant",
          "description": string,
          "severity": "low" | "medium" | "high" | "critical",
          "remediation": string
        }
      ],
      "remediation_recommendations": [string],
      "detailed_analysis": string
    }
  },
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
  },
  "risk_prioritization": {
    "critical": [string],
    "high": [string],
    "medium": [string],
    "low": [string]
  }
}"""

PRODUCT_DEEP_ANALYSIS_PROMPT = f"""You are a senior legal and compliance analyst. Given per-document deep analyses for a product, produce a comprehensive cross-document assessment that a legal team can act on.

## Input
You receive rich summaries of each document's risk breakdown and critical clauses.

## Your task

### 1. CROSS-DOCUMENT ANALYSIS
Identify:
- **Contradictions**: Where two documents make genuinely conflicting statements about the same topic. Do NOT flag as contradictions where one document is simply silent on a topic; only flag when the documents actively conflict.
  - Include exactly what each document says (document_a_statement, document_b_statement).
  - Include the user-facing impact and a concrete recommendation.
- **Information gaps**: Policy areas a user would expect to be covered that no document addresses.
- **Document relationships**: How documents reference, supersede, or complement each other. Cite specific text.

### 2. ENHANCED COMPLIANCE
Assess each relevant regulation (GDPR, CCPA, PIPEDA, LGPD) across all documents combined.
Only include regulations for which the product is plausibly in scope (e.g., GDPR if any EU users are mentioned or if the company operates in the EU).

For each regulation:
- List specific violations with severity and actionable remediation steps.
- List strengths (requirements clearly met with evidence).
- Write a detailed_analysis paragraph (3-5 sentences) summarising overall compliance posture.
- Score 0-10: 0 = fully non-compliant, 10 = fully compliant.

### 3. BUSINESS IMPACT
For **individuals**: What does this mean for a typical user's privacy and legal exposure?
- Assign an overall privacy_risk_level.
- Summarise what data exposure actually means in practice.
- Provide prioritised, specific actions the user can take right now.

For **businesses** considering this vendor/platform:
- Score liability exposure, contract risk (onerous/unusual terms), and vendor risk (data handling practices).
- Describe financial, reputational, and operational risk concretely.
- Provide prioritised actions for procurement/legal review.

### 4. RISK PRIORITIZATION
Rank all identified risks across all documents by severity.
- **critical**: Immediate action required — significant user harm or legal exposure.
- **high**: Serious risk — should be addressed before widespread adoption.
- **medium**: Notable concern — worth monitoring or mitigating.
- **low**: Minor or standard-for-industry risk.

Each entry must be specific (cite the document and clause/practice), not generic.

## Non-negotiable rules
- Use ONLY the evidence provided in the document summaries below.
- Cite your sources: reference documents by type (e.g., "Privacy Policy", "Terms of Service").
- Scope matters: a risk in a global policy ranks higher than the same risk in a product-specific policy.
- Do not invent requirements or fabricate compliance violations.

Return valid JSON strictly matching this schema:
{PRODUCT_DEEP_ANALYSIS_JSON_SCHEMA}
"""
