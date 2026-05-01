"""
Document Classification Analyzer

Specialized analyzer for classifying policy documents through multiple detection methods:
URL pattern analysis, metadata inspection, content heuristics, and LLM fallback.
"""

import json
import re
from typing import Any

from src.core.logging import get_logger
from src.llm import acompletion_with_fallback
from src.utils.llm_usage import usage_tracking
from src.utils.llm_usage_tracking_mixin import LLMUsageTrackingMixin

logger = get_logger(__name__, component="document classification")

# Shared between static content routing and LLM sanity checks (one vocabulary, no parallel heuristics).
POLICY_KEYWORD_SAMPLE_CHARS = 2000
MIN_POLICY_KEYWORD_HITS = 3
# Same minimum body length as metadata-based classification in this module.
MIN_CHARS_SUBSTANTIVE_POLICY_BODY = 300

POLICY_DOC_KEYWORDS: dict[str, list[str]] = {
    "privacy_policy": [
        "personal information",
        "personal data",
        "data collection",
        "data processing",
        "data sharing",
        "data retention",
        "privacy rights",
        "your rights",
        "data protection",
        "information we collect",
        "we collect information",
        "data subject rights",
        "privacy choices",
        "opt-out",
        "data minimization",
        "purpose limitation",
        "données personnelles",
        "datos personales",
        "dati personali",
        "personenbezogene daten",
    ],
    "terms_of_service": [
        "terms of service",
        "terms and conditions",
        "user agreement",
        "service agreement",
        "acceptance of terms",
        "by using our service",
        "governing law",
        "jurisdiction",
        "applicable law",
        "dispute resolution",
        "arbitration",
        "binding arbitration",
        "limitation of liability",
        "liabilities limited",
        "no warranties",
        "indemnification",
        "indemnify",
        "hold harmless",
        "termination",
        "account suspension",
        "service discontinuation",
        "conditions générales",
        "términos y condiciones",
        "condizioni generali",
        "allgemeine geschäftsbedingungen",
    ],
    "cookie_policy": [
        "cookie policy",
        "cookies we use",
        "cookie consent",
        "tracking technologies",
        "third-party cookies",
        "first-party cookies",
        "web beacons",
        "pixel tags",
        "tracking pixels",
        "analytics cookies",
        "functional cookies",
        "advertising cookies",
        "cookie preferences",
        "cookie settings",
        "manage cookies",
        "politique de cookies",
        "política de cookies",
        "cookie-richtlinie",
    ],
    "copyright_policy": [
        "copyright",
        "copyright infringement",
        "dmca",
        "takedown notice",
        "intellectual property",
        "content ownership",
        "user content license",
        "fair use",
        "copyright protection",
        "copyright claims",
    ],
    "data_processing_agreement": [
        "data processing agreement",
        "dpa",
        "data processor",
        "data controller",
        "sub-processor",
        "data processing activities",
        "processing purposes",
        "data security measures",
    ],
    "gdpr_policy": [
        "gdpr",
        "general data protection regulation",
        "data protection officer",
        "dpo",
        "data protection impact assessment",
        "eu data protection",
        "european data protection",
        "article 17",
        "right to erasure",
    ],
    "security_policy": [
        "security practices",
        "security policy",
        "information security",
        "trust center",
        "security controls",
        "technical and organizational measures",
        "encryption in transit",
        "encryption at rest",
        "data encryption",
        "vulnerability disclosure",
        "responsible disclosure",
        "bug bounty",
        "penetration test",
        "security audit",
        "security assessment",
        "soc 2",
        "iso 27001",
        "iso 27018",
        "access logging",
        "access management",
        "intrusion detection",
        "security incident",
        "incident management",
        "incident response",
        "unauthorized access",
        "unauthorized disclosure",
        "security monitoring",
        "vulnerability scan",
        "two-factor authentication",
        "multi-factor authentication",
        "business continuity",
        "disaster recovery",
    ],
    "community_guidelines": [
        "safety policy",
        "community guidelines",
        "acceptable use policy",
        "prohibited content",
        "harassment",
        "abuse",
        "spam",
        "content moderation",
        "reporting abuse",
        "platform rules",
        "transparency center",
        "transparency report",
        "safety center",
        "enforcement",
        "appeals",
    ],
    "children_privacy_policy": [
        "children's privacy",
        "children privacy",
        "child privacy",
        "kids privacy",
        "coppa",
        "parental consent",
        "under 13",
        "under 16",
        "minor",
        "privacy for children",
    ],
}

_ALL_POLICY_KEYWORDS: frozenset[str] = frozenset(
    kw for keywords in POLICY_DOC_KEYWORDS.values() for kw in keywords
)


class DocumentClassifier(LLMUsageTrackingMixin):
    """
    AI-powered document classifier for determining policy document types.

    Uses a multi-layered approach prioritizing speed and accuracy:
    1. URL pattern analysis (fastest)
    2. Metadata keyword matching
    3. Content heuristics with scoring
    4. LLM analysis (fallback)
    """

    def __init__(self, max_content_length: int = 5000):
        super().__init__()
        self.max_content_length = max_content_length

        # Document type categories for classification
        # Must stay in sync with DocType in models/document.py.
        # terms_of_use and terms_and_conditions are intentionally absent:
        # the classifier maps all such URLs/metadata to terms_of_service.
        self.categories = [
            "privacy_policy",
            "terms_of_service",
            "cookie_policy",
            "data_processing_agreement",
            "gdpr_policy",
            "copyright_policy",
            "community_guidelines",
            "children_privacy_policy",
            "security_policy",
            "other",
        ]

        # Basic policy/legal content indicators for URL pattern verification
        self.legal_indicators = [
            "effective date",
            "last updated",
            "governing law",
            "jurisdiction",
            "dispute",
            "liability",
            "indemnification",
        ]

        # Navigation indicators to avoid false positives
        self.nav_indicators = ["home", "about", "contact", "menu", "navigation", "search"]

    @staticmethod
    def _content_supports_substantive_policy_claim(text: str) -> bool:
        """True if the body matches the same keyword model used for non-LLM content routing.

        Used to guard LLM optimism when classification is a broad bucket (community_guidelines,
        other): we only keep ``is_policy_document`` if the text shows enough cross-type policy
        vocabulary in the same window as ``classify_document`` step 3.
        """
        if len(text) < MIN_CHARS_SUBSTANTIVE_POLICY_BODY:
            return False
        sample = text.lower()[:POLICY_KEYWORD_SAMPLE_CHARS]
        hits = sum(1 for kw in _ALL_POLICY_KEYWORDS if kw in sample)
        return hits >= MIN_POLICY_KEYWORD_HITS

    async def classify_document(
        self, url: str, text: str, metadata: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Classify if document is a policy document and determine its type.

        Priority order:
        1. Check URL patterns for document type indicators
        2. Check metadata (title, description) for document type
        3. Check content heuristics (keywords, structure)
        4. Use LLM analysis (only if needed)

        Args:
            url: Document URL
            text: Document content
            metadata: Document metadata

        Returns:
            Dict containing classification, justification, and is_policy_document flag
        """
        # 1. Pre-filter using URL patterns (very fast, no LLM needed)
        url_lower = url.lower()
        url_patterns = {
            "privacy_policy": [
                # Core patterns with optional suffixes
                r"/(?:privacy|data[-_]protection)(?:[-_]?(?:policy|notice|statement|agreement))?(?:/\w+)*",
                # Versioned and nested URLs
                r"/legal/privacy(?:/\w+)*",
                r"/policies/privacy(?:/\w+)*",
                r"/documents/privacy(?:/\w+)*",
                # International variations
                r"/datenschutz(?:erklärung)?",  # German
                r"/politique-de-confidentialite",  # French
                r"/politica-de-privacidad",  # Spanish
                r"/informativa-sulla-privacy",  # Italian
                r"/privacidad",  # Spanish (shorter)
                r"/privacy-statement",
                r"/privacy-notice",
            ],
            "terms_of_service": [
                # Core patterns with optional suffixes
                r"/terms?(?:[-_]?(?:of[-_]service|and[-_]conditions?|service|conditions?))?(?:/\w+)*",
                # Common variations
                r"/tos(?:/\w+)*",
                r"/legal/terms?(?:/\w+)*",
                r"/policies/terms?(?:/\w+)*",
                r"/documents/terms?(?:/\w+)*",
                # International variations
                r"/nutzungsbedingungen",  # German
                r"/conditions-d-utilisation",  # French
                r"/terminos-de-servicio",  # Spanish
                r"/condizioni-di-servizio",  # Italian
                r"/terms-of-use",
                r"/user-agreement",
                r"/service-agreement",
            ],
            "cookie_policy": [
                # Core patterns with variations
                r"/cookie(?:s)?(?:[-_]?(?:policy|notice|statement|richtlinie))?(?:/\w+)*",
                r"/legal/cookie(?:s)?(?:/\w+)*",
                r"/policies/cookie(?:s)?(?:/\w+)*",
                r"/cookie-richtlinie",  # German
                r"/politique-de-cookies",  # French
                r"/politica-de-cookies",  # Spanish/Portuguese
                r"/cookie-notice",
                r"/cookie-statement",
            ],
            "copyright_policy": [
                # Core patterns
                r"/copyright(?:[-_]?(?:policy|notice|statement))?(?:/\w+)*",
                r"/dmca(?:/\w+)*",
                r"/legal/copyright(?:/\w+)*",
                r"/policies/copyright(?:/\w+)*",
                r"/intellectual-property",
                r"/ip-policy",
            ],
            "data_processing_agreement": [
                r"/dpa(?:/\w+)*",
                r"/data-processing-agreement(?:/\w+)*",
                r"/data-processing",
                r"/processing-agreement",
            ],
            "gdpr_policy": [
                r"/gdpr(?:/\w+)*",
                r"/eu-privacy",
                r"/european-privacy",
            ],
            "security_policy": [
                r"/security(?:[-_]?(?:practices|policy|overview|whitepaper|statement))?(?:/\w+)*",
                r"/trust(?:/\w+)*",
                r"/legal/security(?:/\w+)*",
                r"/policies/security(?:/\w+)*",
                r"/security-center",
                r"/safety-and-security",
                r"/vulnerability(?:[-_]disclosure)?",
                r"/responsible[-_]disclosure",
            ],
            "community_guidelines": [
                r"/safety(?:[-_]?(?:policy|guidelines|standards))?(?:/\w+)*",
                r"/community-guidelines",
                r"/content-policy",
                r"/community(?:[-_]?guidelines|[-_]?standards|[-_]?safety)?(?:/\w+)*",
                r"/transparency(?:[-_]?center|[-_]?report|[-_]?hub|[-_]?policy|[-_]?safety)?(?:/\w+)*",
                r"/rules?(?:/\w+)*",
                r"/guidelines?(?:/\w+)*",
            ],
            "children_privacy_policy": [
                r"/children(?:['-]?s)?[-_]privacy(?:[-_]?(?:policy|notice))?(?:/\w+)*",
                r"/kids[-_]privacy",
                r"/child(?:ren)?[-_]privacy",
                r"/coppa",
            ],
        }

        for doc_type, patterns in url_patterns.items():
            for pattern in patterns:
                if re.search(pattern, url_lower):
                    # Verify it's actually a substantive policy document (not just a link)
                    text_lower = text.lower()
                    has_legal_content = any(
                        indicator in text_lower for indicator in self.legal_indicators
                    )

                    if has_legal_content or len(text) > 500:  # Substantive content
                        logger.debug(f"matched URL pattern '{pattern}': classified as {doc_type}")
                        return {
                            "classification": doc_type,
                            "classification_justification": f"Detected from URL pattern: {pattern}",
                            "is_policy_document": True,
                            "is_policy_document_justification": "URL pattern and content indicate substantive policy document",
                        }

        # 2. Check metadata for document type indicators
        if metadata:
            title = (metadata.get("title") or "").lower()
            description = (
                metadata.get("description") or metadata.get("og:description") or ""
            ).lower()
            combined_meta = f"{title} {description}"

            meta_keywords = {
                "privacy_policy": [
                    "privacy policy",
                    "privacy notice",
                    "privacy statement",
                    "data protection",
                    "data privacy",
                    "privacy rights",
                    "datenschutz",
                    "datenschutzerklärung",  # German
                    "politique de confidentialité",  # French
                    "política de privacidad",  # Spanish
                    "informativa sulla privacy",  # Italian
                    "privacy shield",
                    "gdpr compliance",
                ],
                "terms_of_service": [
                    "terms of service",
                    "terms and conditions",
                    "terms of use",
                    "user agreement",
                    "service agreement",
                    "terms & conditions",
                    "tos",
                    "terms",
                    "conditions of use",
                    "nutzungsbedingungen",  # German
                    "conditions d'utilisation",  # French
                    "términos de servicio",
                    "términos y condiciones",  # Spanish
                    "condizioni di servizio",  # Italian
                    "user terms",
                    "service terms",
                ],
                "cookie_policy": [
                    "cookie policy",
                    "cookie notice",
                    "cookie statement",
                    "cookie consent",
                    "cookie settings",
                    "cookie preferences",
                    "cookies policy",
                    "cookie richtlinie",  # German
                    "politique de cookies",  # French
                    "política de cookies",  # Spanish/Portuguese
                    "cookie banner",
                    "cookie management",
                ],
                "copyright_policy": [
                    "copyright",
                    "copyright policy",
                    "copyright notice",
                    "dmca",
                    "dmca policy",
                    "digital millennium copyright act",
                    "intellectual property",
                    "ip policy",
                    "content rights",
                    "copyright infringement",
                    "copyright protection",
                ],
                "data_processing_agreement": [
                    "data processing agreement",
                    "dpa",
                    "data processing addendum",
                    "processing agreement",
                    "data processor agreement",
                ],
                "gdpr_policy": [
                    "gdpr",
                    "gdpr policy",
                    "eu privacy",
                    "european privacy",
                    "general data protection regulation",
                ],
                "security_policy": [
                    "security practices",
                    "security policy",
                    "information security",
                    "trust center",
                    "security overview",
                    "data security",
                    "security and compliance",
                ],
                "community_guidelines": [
                    "safety policy",
                    "community guidelines",
                    "content policy",
                    "acceptable use",
                    "community standards",
                    "platform rules",
                    "transparency center",
                    "transparency report",
                    "safety center",
                    "enforcement",
                    "appeals",
                ],
                "children_privacy_policy": [
                    "children's privacy",
                    "children privacy",
                    "child privacy",
                    "kids privacy",
                    "coppa",
                    "privacy for children",
                ],
            }

            for doc_type, keywords in meta_keywords.items():
                if any(keyword in combined_meta for keyword in keywords):
                    # Check if content is substantial (not just a navigation page)
                    if len(text) > 300:
                        logger.debug(f"found metadata keyword matches: classified as {doc_type}")
                        return {
                            "classification": doc_type,
                            "classification_justification": "Detected from metadata keywords",
                            "is_policy_document": True,
                            "is_policy_document_justification": "Metadata and content indicate substantive policy document",
                        }

        # 3. Check content heuristics (keywords and structure)
        text_lower = text.lower()
        text_sample = text_lower[:POLICY_KEYWORD_SAMPLE_CHARS]

        # Count matches for each document type
        doc_type_scores: dict[str, int] = {}
        for doc_type, keywords in POLICY_DOC_KEYWORDS.items():
            score = sum(1 for keyword in keywords if keyword in text_sample)
            if score > 0:
                doc_type_scores[doc_type] = score

        # If we have strong indicators, classify without LLM
        if doc_type_scores:
            best_type = max(doc_type_scores.items(), key=lambda x: x[1])
            if best_type[1] >= 3:  # At least 3 keyword matches
                # Verify it's not just a navigation/link page (trust/security pages often use
                # "publish date" / "last revised" instead of "effective date").
                has_doc_structure = (
                    "effective" in text_sample
                    or "last updated" in text_sample
                    or "publish date" in text_sample
                    or "published:" in text_sample
                    or "last revised" in text_sample
                )
                if len(text) > 500 and has_doc_structure:
                    logger.debug(
                        f"matched content heuristics (score: {best_type[1]}): classified as {best_type[0]}"
                    )
                    return {
                        "classification": best_type[0],
                        "classification_justification": f"Detected from content keywords (score: {best_type[1]})",
                        "is_policy_document": True,
                        "is_policy_document_justification": "Content keywords and structure indicate substantive policy document",
                    }

        # 4. Quick rejection: If content is too short or lacks policy/legal structure, likely not useful
        if len(text) < 200:
            logger.debug("document content too short to be a policy document (less than 200 chars)")
            return {
                "classification": "other",
                "classification_justification": "Document too short to be substantive policy content",
                "is_policy_document": False,
                "is_policy_document_justification": "Content length indicates this is not a policy document",
            }

        # Check for navigation/page structure indicators (not policy documents)
        if (
            any(indicator in text_lower[:500] for indicator in self.nav_indicators)
            and len(text) < 1000
        ):
            logger.debug("detected navigation or page structure elements; not a policy document")
            return {
                "classification": "other",
                "classification_justification": "Content structure indicates navigation/page, not a policy document",
                "is_policy_document": False,
                "is_policy_document_justification": "Lacks substantive policy content structure",
            }

        # 5. Use LLM for classification (only if pre-filtering couldn't determine)
        logger.debug("could not classify document statically; invoking LLM for classification")
        content_sample = text[: self.max_content_length]
        categories_list = "\n".join(f"- {cat}" for cat in self.categories)

        prompt = f"""Analyze webpage content to determine if it's a policy document and classify its type.

URL: {url}
Content: {content_sample}
Metadata: {json.dumps(metadata, indent=2)}

Categories:
{categories_list}

Return JSON with:
- classification: most appropriate category (use "other" if not a policy document or unclear)
- classification_justification: brief explanation of category choice
- is_policy_document: boolean (True only for substantive policy documents like privacy policies, terms of service, cookie policies, safety policies, community guidelines, etc.)
- is_policy_document_justification: rationale for policy document classification

Example output:
{{
  "classification": "privacy_policy",
  "classification_justification": "The content is a privacy policy for a website.",
  "is_policy_document": true,
  "is_policy_document_justification": "The content is a privacy policy for a website."
}}

Note: Cookie banners, navigation elements, or links to policy documents don't count as policy documents themselves.
Security practices / trust pages (encryption, audits, incident response, certifications) are policy documents — use security_policy."""

        system_prompt = """You are a policy document classifier. Identify substantive policy content (privacy, terms, cookies, security/trust practices, safety policies, community guidelines, etc.) and categorize accurately."""

        try:
            async with usage_tracking(self._create_usage_tracker("classify_document")):
                response = await acompletion_with_fallback(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
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

            result = json.loads(content)
            logger.debug(
                f"LLM classification result: {result['classification']} (is_policy: {result['is_policy_document']})"
            )

            allowed = frozenset(self.categories)
            classification = result.get("classification", "other")
            if classification not in allowed:
                classification = "other"
                result["classification"] = "other"
                prev_c = (result.get("classification_justification") or "").strip()
                result["classification_justification"] = (
                    f"{prev_c} (normalized unknown label to other)".strip()
                    if prev_c
                    else "Unknown label normalized to other"
                )
            # Downgrade only community_guidelines: broad bucket + LLM optimism. Do not apply
            # the vocabulary bar to "other" — substantive but unclassifiable policies must stay ingestible.
            if result.get("is_policy_document") and classification == "community_guidelines":
                if not self._content_supports_substantive_policy_claim(text):
                    result["is_policy_document"] = False
                    prev = (result.get("is_policy_document_justification") or "").strip()
                    suffix = (
                        "Content does not meet the same keyword-and-length bar used for "
                        "non-LLM policy detection (insufficient policy vocabulary or body length)."
                    )
                    result["is_policy_document_justification"] = (
                        f"{prev} {suffix}".strip() if prev else suffix
                    )

            return result  # type: ignore

        except Exception as e:
            logger.warning(f"classification process failed: {e}")
            return {
                "classification": "other",
                "classification_justification": f"Classification failed: {e}",
                "is_policy_document": False,
                "is_policy_document_justification": "Could not analyze due to error",
            }
