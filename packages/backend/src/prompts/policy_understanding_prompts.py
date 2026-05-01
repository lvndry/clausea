"""Policy understanding — **interactive chat retrieval** (embedding search).

## Where this runs in the product

- **Product page (`/products/{slug}`)** — After crawl, the pipeline runs per-document
  analysis then `generate_product_overview()` in `analyser.py`. That synthesis (prompts in
  `analysis_prompts.py`) is **cached on the product** and powers the dashboard overview.
  **No Pinecone query** is required to load the page.

- **Chat / agent** — When the user asks follow-up questions, `search_query` and optionally
  `analyze_policy_documents` in `agent/tools.py` **embed** natural-language queries and
  search the vector index (Pinecone). The **dimension queries** in this module are used
  only there, to gather chunks for a one-off “what does this mean for me?” pass.

Keep the dimension list aligned in *theme* with what the batch overview cares about
(data, sale, children, grants to the company, government access, etc.), but do not assume
the two paths share code — they are complementary surfaces.

This module is **not** a legal compliance audit. Optional regulation context in chat is
educational framing only.
"""

from __future__ import annotations

from typing import NamedTuple


class PolicyCorpusDimension(NamedTuple):
    """One cross-document slice of the user-understanding model.

    Each dimension carries one or more natural-language strings for vector search.
    Multiple strings per dimension are optional (e.g. split very different phrasings);
    the default is one dense query per dimension to limit parallel search fan-out.
    """

    id: str
    """Stable key for logging, tests, or future doc-type weighting."""
    covers: str
    """What kinds of clauses this dimension is meant to surface (product documentation)."""
    queries: tuple[str, ...]
    """Embedding queries; typically one combined string per dimension."""


# ---------------------------------------------------------------------------
# Corpus retrieval — one primary query per dimension (~parallel searches).
# Wording is intentionally broad so the same dimension helps across doc types.
# ---------------------------------------------------------------------------

POLICY_CORPUS_DIMENSIONS: tuple[PolicyCorpusDimension, ...] = (
    PolicyCorpusDimension(
        id="scope_and_eligibility",
        covers="Who the policies apply to, age limits, account creation, definitions.",
        queries=(
            "who these terms apply to eligible age account registration user definitions "
            "scope of agreement jurisdiction",
        ),
    ),
    PolicyCorpusDimension(
        id="children_teens_and_family",
        covers="Minors, teens, parental consent, child safety, age-gated or family products.",
        queries=(
            "children under 13 minor teen adolescent parental consent guardian COPPA age "
            "requirement child safety family account teen experience school student",
        ),
    ),
    PolicyCorpusDimension(
        id="personal_information",
        covers="Data or information collected, categories, sources (privacy, ToS, onboarding).",
        queries=(
            "personal information data collected categories sources voluntarily provided "
            "automatically collected device information logs activity",
        ),
    ),
    PolicyCorpusDimension(
        id="use_and_sharing",
        covers="How data or information is used, shared, or disclosed; partners and advertising.",
        queries=(
            "how information used disclosed shared third parties service providers partners "
            "advertising marketing profiling analytics business purposes cross-app",
        ),
    ),
    PolicyCorpusDimension(
        id="data_sale_and_monetization",
        covers="Sale or licensing of personal data, data brokers, monetary or valuable consideration.",
        queries=(
            "sell sale personal information monetary consideration valuable consideration "
            "data broker share for compensation targeted ads audience monetization",
        ),
    ),
    PolicyCorpusDimension(
        id="grants_to_organization",
        covers="Licenses and permissions users give the company: content, data use, product access, AI.",
        queries=(
            "license grant permission irrevocable perpetual sublicense royalty free use your "
            "content data train machine learning artificial intelligence model scanning "
            "access contacts calendar photos microphone camera location clipboard",
        ),
    ),
    PolicyCorpusDimension(
        id="retention_and_deletion",
        covers="How long data is kept; account or data deletion.",
        queries=(
            "retention period how long data stored delete account erasure remove information "
            "data retention schedule",
        ),
    ),
    PolicyCorpusDimension(
        id="tracking_and_cookies",
        covers="Cookies, pixels, analytics, similar technologies, advertising IDs.",
        queries=(
            "cookies similar technologies tracking pixels analytics advertising identifiers "
            "preferences opt out browser signals",
        ),
    ),
    PolicyCorpusDimension(
        id="conduct_and_rules",
        covers="Acceptable use, prohibited conduct, community rules, behavioral obligations.",
        queries=(
            "acceptable use prohibited conduct restrictions violations rules behavior "
            "community guidelines standards enforcement",
        ),
    ),
    PolicyCorpusDimension(
        id="content_and_intellectual_property",
        covers="User content license, moderation, copyright, trademarks, DMCA.",
        queries=(
            "user content license grant moderation remove copyright intellectual property "
            "dmca trademark ownership posting",
        ),
    ),
    PolicyCorpusDimension(
        id="safety_and_harm",
        covers="Physical and online safety, risky activities, reporting abuse, harmful content.",
        queries=(
            "safety harmful content risk injury reporting abuse harassment hateful content "
            "violence self-harm dangerous activities challenge stunt moderation escalation",
        ),
    ),
    PolicyCorpusDimension(
        id="government_access_and_sensitive_processing",
        covers="Law enforcement and legal requests, emergency disclosure, sensitive categories, "
        "inference, automated decisions, and collection readers often treat as high-stakes.",
        queries=(
            "law enforcement government request subpoena warrant court order national security "
            "preserve disclose emergency lawful access criminal investigation "
            "biometric facial voice health genetic precise geolocation racial ethnic origin "
            "sexual orientation political belief religion trade union inference sensitive "
            "special category automated decision solely automated profiling significant effects "
            "workplace employer school monitoring",
        ),
    ),
    PolicyCorpusDimension(
        id="account_and_service_control",
        covers="Suspension, termination, service changes, availability.",
        queries=(
            "suspend terminate disable account end service availability changes discontinue "
            "limit access consequences",
        ),
    ),
    PolicyCorpusDimension(
        id="user_rights_and_contact",
        covers="Access, correction, opt-out, complaints, contact, appeals (as described in text).",
        queries=(
            "your rights access correct opt out unsubscribe contact privacy support complaint "
            "appeal request how to exercise",
        ),
    ),
    PolicyCorpusDimension(
        id="security_and_incidents",
        covers="Security practices, breaches, incident notification (as described).",
        queries=(
            "security measures safeguards protect data breach incident notification "
            "unauthorized access vulnerability",
        ),
    ),
    PolicyCorpusDimension(
        id="international_and_law",
        covers="Cross-border transfers, regional terms, governing law, jurisdiction.",
        queries=(
            "international transfer outside country region specific terms governing law "
            "jurisdiction venue applicable law",
        ),
    ),
    PolicyCorpusDimension(
        id="disputes_and_liability",
        covers="Dispute resolution, arbitration, class waivers, limitations of liability.",
        queries=(
            "dispute resolution arbitration class action waiver mediation informal claim "
            "limitation of liability disclaimer damages",
        ),
    ),
    PolicyCorpusDimension(
        id="changes_and_notice",
        covers="How policies are updated, effective dates, notice to users.",
        queries=(
            "changes updates modifications policy revision effective date notice notify users "
            "continued use consent",
        ),
    ),
)


def iter_policy_corpus_retrieval_queries() -> list[str]:
    """Flatten all dimension queries for parallel embedding search."""
    return [q for dimension in POLICY_CORPUS_DIMENSIONS for q in dimension.queries]


USER_POLICY_RETRIEVAL_QUERIES: list[str] = iter_policy_corpus_retrieval_queries()

POLICY_USER_ANALYSIS_JSON_SCHEMA = """{
  "headline_summary": string,
  "what_you_agree_to": [string],
  "risks_and_watchouts": [
    {"title": string, "detail": string, "severity": "low" | "medium" | "high"}
  ],
  "unusual_or_notable_clauses": [string],
  "your_rights_and_choices": [string],
  "whats_unclear_or_missing": [string],
  "regulation_plain_language_note": string | null,
  "limitations": string
}"""

POLICY_USER_ANALYSIS_PROMPT = """You help thoughtful readers (not lawyers) understand **published policy documents** in practice.

The excerpts below may come from **any mix** of document types: privacy policy, terms of service, cookie policy, community guidelines, safety policy, transparency pages, etc. **Only discuss what the excerpts actually support.** If a whole category (e.g. data collection) does not appear because the crawl is terms-only or guidelines-only, say so under whats_unclear_or_missing or limitations — do not invent.

Context — labeled SOURCE[N] with url, document type, and char offsets:
{context}

User focus (may be empty — if empty, cover the full picture based on what is in the excerpts):
{focus}

Regulation angle (may be empty):
{regulation_context}

Instructions:
- Plain, direct language. Explain jargon when you must use it.
- **what_you_agree_to**: concrete bullets — including **behavioral rules** (ToS/guidelines) and **data/service permissions** (privacy), only as stated in the text.
- **risks_and_watchouts**: what a privacy- and fairness-minded reader should notice — including, when evidenced: **sale or monetization of data**, **broad grants** (e.g. content/AI training, deep product access), **children/teens** rules, **safety** tradeoffs, **government or legal disclosure**, **sensitive or invasive collection** (biometrics, precise location, inference, automated decisions, monitoring contexts). Never accuse the organization of illegality; describe what the text permits or describes. Tie to evidence. **severity** = practical user impact if the text says what you describe.
- **unusual_or_notable_clauses**: surprising or unusually broad/narrow terms vs typical consumer-facing bundles — only with support in the excerpts.
- **your_rights_and_choices**: what the documents say users may do (appeal, delete, report, opt out, etc.), without inventing legal rights.
- **whats_unclear_or_missing**: important user questions left vague or absent **in these excerpts** (not the same as illegal).
- **regulation_plain_language_note**: If a regulation angle was given, 2–4 sentences comparing retrieved text to what people often expect in notices under that framework — educational only, **never** claim compliance or non-compliance. If no regulation angle, null.
- **limitations**: partial corpus; operational reality may differ; not legal advice.

Rules:
- Evidence only. No fabrication.
- Tie claims mentally to SOURCE[N]; sources are listed separately for the user.

Output JSON matching this schema:
{schema}
"""
