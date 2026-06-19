"""Content-based policy document analysis."""

import re
from typing import Any


class ContentAnalyzer:
    """Analyzes page content for policy document characteristics."""

    def __init__(self) -> None:
        self.compiled_legal_phrases = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in [
                r"by using (?:this|our) (?:service|website|platform)",
                r"you agree to (?:these|our) terms",
                r"we (?:collect|process|use) your (?:personal )?(?:data|information)",
                r"this policy (?:describes|explains) how we",
                r"we may (?:update|modify|change) this policy",
                r"your (?:privacy|data|personal information) is important",
                r"we are committed to protecting your privacy",
                r"cookies (?:are|help us)",
                r"you have the right to",
                r"data retention period",
                r"lawful basis for processing",
                r"data processing addendum",
                r"this addendum (?:forms|supplements|amends)",
                r"subprocessor(?:s)? (?:list|agreement)",
                r"we (?:engage|use) (?:third.party|sub.?processor)",
                r"processing (?:activities|operations|purposes)",
                r"data subject (?:rights|requests)",
                r"cross.border (?:transfer|data transfer)",
                r"adequacy decision",
                r"standard contractual clauses",
                r"security (?:measures|safeguards|controls)",
                r"data (?:breach|incident) (?:notification|response)",
                r"controller (?:and|to) processor",
                r"processor (?:instructions|obligations)",
            ]
        ]

        self.quick_check_pattern = re.compile(
            r"\b(?:privacy|terms|policy|agreement|legal|gdpr|ccpa|cookie|data protection|"
            r"liability|disclaimer|jurisdiction|compliance|consent|rights)\b",
            re.IGNORECASE,
        )

        self.legal_indicators = [
            "terms of service",
            "privacy policy",
            "cookie policy",
            "data protection",
            "personal information",
            "third parties",
            "we collect",
            "your rights",
            "lawful basis",
            "consent",
            "legitimate interest",
            "data controller",
            "data processor",
            "retention period",
            "delete your data",
            "opt out",
            "agreement",
            "binding",
            "governing law",
            "jurisdiction",
            "liability",
            "disclaimer",
            "limitation of liability",
            "indemnification",
            "intellectual property",
            "copyright",
            "trademark",
            "infringement",
            "compliance",
            "regulatory",
            "gdpr",
            "ccpa",
            "hipaa",
            "coppa",
            "data processing addendum",
            "dpa",
            "subprocessor",
            "subprocessors",
            "sub-processor",
            "sub-processors",
            "vendor",
            "suppliers",
            "third party service provider",
            "service provider",
            "data transfer",
            "international transfer",
            "adequacy decision",
            "standard contractual clauses",
            "scc",
            "binding corporate rules",
            "bcr",
            "data subject rights",
            "data security",
            "data breach",
            "processing activities",
            "personal data",
            "special categories",
            "sensitive data",
            "transparency report",
        ]

        self.title_keywords = [
            "terms",
            "privacy",
            "policy",
            "cookie",
            "legal",
            "agreement",
            "data",
            "gdpr",
        ]

    def analyze_content(
        self, content: str, title: str = "", metadata: dict[str, Any] | None = None
    ) -> tuple[bool, float, list[str]]:
        if not content:
            return False, 0.0, []

        word_count = len(content.split())
        char_count = len(content)

        if word_count < 50 or char_count < 300:
            return False, 0.0, ["content_too_short"]

        if not self.quick_check_pattern.search(content):
            return False, 0.0, ["no_policy_keywords"]

        content_lower = content.lower()
        title_lower = title.lower() if title else ""

        matched_indicators = []
        raw_score = 0.0
        matched_content_chars = 0

        for indicator in self.legal_indicators:
            if indicator in content_lower:
                matched_indicators.append(indicator)
                raw_score += 1.0
                matched_content_chars += len(indicator) * content_lower.count(indicator)

        for compiled_pattern in self.compiled_legal_phrases:
            matches = compiled_pattern.finditer(content_lower)
            for match in matches:
                matched_indicators.append(compiled_pattern.pattern)
                raw_score += 2.0
                matched_content_chars += len(match.group())

        legal_density = matched_content_chars / char_count

        title_bonus = 0.0
        for keyword in self.title_keywords:
            if keyword in title_lower:
                title_bonus += 3.0
                matched_indicators.append(f"title:{keyword}")

        metadata_bonus = 0.0
        if metadata:
            meta_title = metadata.get("title", "").lower()
            meta_description = metadata.get("description", "").lower()

            for text in [meta_title, meta_description]:
                for keyword in self.title_keywords:
                    if keyword in text:
                        metadata_bonus += 1.0

        base_score = raw_score * legal_density * 100
        final_score = base_score + title_bonus + metadata_bonus

        normalized_score = min(10.0, final_score)

        min_density_threshold = 0.05
        min_score_threshold = 2.0

        is_policy = (
            (legal_density >= min_density_threshold and normalized_score >= min_score_threshold)
            or title_bonus >= 6.0
        )

        matched_indicators.append(f"density:{legal_density:.3f}")
        matched_indicators.append(f"word_count:{word_count}")

        return is_policy, normalized_score, matched_indicators
