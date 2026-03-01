"""
Region Detection Analyzer

Specialized analyzer for detecting geographic/regional applicability of legal documents
through URL patterns, compliance frameworks, explicit mentions, and jurisdiction clauses.
"""

import json
import re
from typing import Any

from src.core.logging import get_logger
from src.models.document import Region

logger = get_logger(__name__, component="region detection")


class RegionDetector:
    """
    AI-powered region detector for determining document geographic applicability.

    Uses a multi-layered approach prioritizing speed and accuracy:
    1. URL pattern analysis
    2. Metadata analysis
    3. Content analysis (compliance frameworks, explicit mentions, jurisdiction)
    """

    def __init__(self):
        # URL region patterns for common website structures
        self.url_region_patterns = {
            r"/eu/": ["EU"],
            r"/europe/": ["EU"],
            r"/uk/": ["UK"],
            r"/gb/": ["UK"],
            r"/us/": ["US"],
            r"/usa/": ["US"],
            r"/ca/": ["Canada"],
            r"/canada/": ["Canada"],
            r"/au/": ["Australia"],
            r"/australia/": ["Australia"],
            r"/br/": ["Brazil"],
            r"/brazil/": ["Brazil"],
            r"/kr/": ["South Korea"],
            r"/korea/": ["South Korea"],
            r"/jp/": ["Asia"],  # Japan
            r"/asia/": ["Asia"],
        }

        # Compliance framework indicators (expanded international coverage)
        self.compliance_frameworks = {
            # European Union
            "GDPR": ["EU", "European Union"],
            "ePrivacy": ["EU", "European Union"],
            "DSA": ["EU", "European Union"],  # Digital Services Act
            "DMA": ["EU", "European Union"],  # Digital Markets Act
            # United States
            "CCPA": ["US"],
            "CPRA": ["US"],  # California Privacy Rights Act (CCPA successor)
            "VCDPA": ["US"],  # Virginia Consumer Data Protection Act
            "CTDPA": ["US"],  # Connecticut Data Privacy Act
            "CPA": ["US"],  # Colorado Privacy Act
            "UCPA": ["US"],  # Utah Consumer Privacy Act
            "FDCPA": ["US"],  # Fair Debt Collection Practices Act
            "GLBA": ["US"],  # Gramm-Leach-Bliley Act (financial privacy)
            "HIPAA": ["US"],  # Health Insurance Portability and Accountability Act
            # Canada
            "PIPEDA": ["Canada"],
            "CASL": ["Canada"],  # Canada's Anti-Spam Legislation
            # South America
            "LGPD": ["Brazil"],
            "PDPL_Argentina": ["Argentina"],  # Personal Data Protection Law
            # Asia-Pacific
            "PDPA": ["Singapore", "South Korea"],
            "APPI": ["Japan"],  # Act on the Protection of Personal Information
            "PIPL": ["China"],  # Personal Information Protection Law
            "PDP_Thailand": ["Thailand"],  # Personal Data Protection Act
            "Privacy_Act_Australia": ["Australia"],
            "POPIA_South_Africa": ["South Africa"],  # Protection of Personal Information Act
            # Middle East
            "PDPL_UAE": ["UAE"],  # Personal Data Protection Law
            "POPIA_Israel": ["Israel"],  # Protection of Privacy in Israel
            # Other frameworks
            "ISO 27001": ["global"],  # Information security management
            "ISO 27701": ["global"],  # Privacy information management
            "SOC 2": ["global"],  # Security, availability, and confidentiality
        }

        # Explicit region mentions (expanded coverage)
        self.region_phrases = {
            # United States
            "for california residents": ["US"],
            "for california users": ["US"],
            "california privacy": ["US"],
            "california consumer privacy act": ["US"],
            "for nevada residents": ["US"],
            "for virginia residents": ["US"],
            "for colorado residents": ["US"],
            "for utah residents": ["US"],
            "for connecticut residents": ["US"],
            "for us residents": ["US"],
            "for united states residents": ["US"],
            # European Union
            "for users in the eu": ["EU"],
            "for european users": ["EU"],
            "for eu residents": ["EU"],
            "for european residents": ["EU"],
            "european economic area": ["EU"],
            "eea residents": ["EU"],
            # United Kingdom
            "for uk residents": ["UK"],
            "for united kingdom residents": ["UK"],
            "for british residents": ["UK"],
            "for england residents": ["UK"],
            "for wales residents": ["UK"],
            "for scotland residents": ["UK"],
            "for northern ireland residents": ["UK"],
            # Canada
            "for canadian users": ["Canada"],
            "for users in canada": ["Canada"],
            "for canadian residents": ["Canada"],
            # Australia
            "for australian users": ["Australia"],
            "for users in australia": ["Australia"],
            "for australian residents": ["Australia"],
            # Brazil
            "for users in brazil": ["Brazil"],
            "for brazilian users": ["Brazil"],
            "for brazilian residents": ["Brazil"],
            # Other countries
            "for japanese users": ["Japan"],
            "for users in japan": ["Japan"],
            "for german users": ["Germany"],
            "for users in germany": ["Germany"],
            "for french users": ["France"],
            "for users in france": ["France"],
            "for spanish users": ["Spain"],
            "for users in spain": ["Spain"],
            "for italian users": ["Italy"],
            "for users in italy": ["Italy"],
            "for mexican users": ["Mexico"],
            "for users in mexico": ["Mexico"],
            "for argentinian users": ["Argentina"],
            "for users in argentina": ["Argentina"],
            "for singapore users": ["Singapore"],
            "for users in singapore": ["Singapore"],
            "for south korean users": ["South Korea"],
            "for users in south korea": ["South Korea"],
            "for chinese users": ["China"],
            "for users in china": ["China"],
            "for indian users": ["India"],
            "for users in india": ["India"],
        }

        # Governing law / jurisdiction patterns
        self.jurisdiction_patterns = [
            (r"governed by the laws of (?:the )?([^,\.]+)", ["UK", "US", "Canada"]),
            (r"jurisdiction.*(?:england|wales|united kingdom)", ["UK"]),
            (r"jurisdiction.*(?:california|new york|united states)", ["US"]),
            (r"jurisdiction.*(?:ontario|british columbia|canada)", ["Canada"]),
        ]

    async def detect_regions(self, text: str, metadata: dict[str, Any], url: str) -> dict[str, Any]:
        """
        Detect if document applies globally or to specific regions.

        Priority order:
        1. Check URL patterns for region indicators
        2. Check metadata for region information
        3. Check content for explicit region mentions and compliance frameworks
        4. Use LLM analysis (only if needed)

        Args:
            text: Document content
            metadata: Document metadata
            url: Document URL

        Returns:
            Dict containing region analysis with mapped region codes
        """
        # 1. Check URL patterns for region indicators
        url_lower = url.lower()

        detected_regions = []
        for pattern, regions in self.url_region_patterns.items():
            if re.search(pattern, url_lower):
                detected_regions.extend(regions)
                logger.debug(f"matched URL pattern '{pattern}': detected regions {regions}")

        if detected_regions:
            mapped_regions = []
            for region in detected_regions:
                mapped = self._map_region_name_to_code(region)
                if mapped and mapped not in mapped_regions:
                    mapped_regions.append(mapped)

            if mapped_regions:
                return {
                    "regions": mapped_regions,
                    "confidence": 0.80,
                    "justification": "Detected from URL pattern",
                    "regional_indicators": [f"URL pattern: {url}"],
                }

        # 2. Check metadata for region information
        if metadata:
            # Check for region-specific metadata
            meta_text = json.dumps(metadata).lower()
            if any(term in meta_text for term in ["eu", "european union", "gdpr"]):
                return {
                    "regions": ["EU"],
                    "confidence": 0.75,
                    "justification": "Detected from metadata (EU/GDPR references)",
                    "regional_indicators": ["Metadata contains EU/GDPR references"],
                }

        # 3. Check content for explicit region mentions and compliance frameworks
        text_lower = text.lower()
        text_sample = text_lower[:3000] if len(text_lower) > 3000 else text_lower

        detected_from_content = []

        # Check compliance frameworks
        for framework, regions in self.compliance_frameworks.items():
            if framework.lower() in text_sample:
                detected_from_content.extend(regions)
                logger.debug(
                    f"matched compliance framework '{framework}': detected regions {regions}"
                )

        # Check explicit region mentions
        for phrase, regions in self.region_phrases.items():
            if phrase in text_sample:
                detected_from_content.extend(regions)
                logger.debug(
                    f"matched explicit region phrase '{phrase}': detected regions {regions}"
                )

        # Check jurisdiction clauses
        for pattern, default_regions in self.jurisdiction_patterns:
            matches = list(re.finditer(pattern, text_sample, re.IGNORECASE))
            if matches:
                # Try to extract specific region from match
                detected_from_content.extend(default_regions)
                logger.debug(f"matched jurisdiction clause: detected regions {default_regions}")

        if detected_from_content:
            # Deduplicate and map regions
            unique_regions = []
            for region in detected_from_content:
                mapped = self._map_region_name_to_code(region)
                if mapped and mapped not in unique_regions:
                    unique_regions.append(mapped)

            if unique_regions:
                return {
                    "regions": unique_regions,
                    "confidence": 0.85,
                    "justification": "Detected from content (compliance frameworks, explicit mentions, or jurisdiction clauses)",
                    "regional_indicators": [f"Content analysis found: {', '.join(unique_regions)}"],
                }

        # 4. Default to global if no specific regions found via pre-filtering
        logger.debug("no specific regions detected; defaulting to global applicability")
        return {
            "regions": ["global"],
            "confidence": 0.70,
            "justification": "No specific regions detected, defaulting to global",
            "regional_indicators": [],
        }

    def _map_region_name_to_code(self, region_name: str) -> Region | None:
        """Map a region name to a Document Region code."""
        region_mapping: dict[str, Region] = {
            "united states": "US",
            "usa": "US",
            "us": "US",
            "america": "US",
            "california": "US",  # California is part of US
            "european union": "EU",
            "eu": "EU",
            "europe": "EU",
            "germany": "EU",
            "france": "EU",
            "spain": "EU",
            "italy": "EU",
            "united kingdom": "UK",
            "uk": "UK",
            "gb": "UK",
            "britain": "UK",
            "england": "UK",
            "wales": "UK",
            "scotland": "UK",
            "northern ireland": "UK",
            "asia": "Asia",
            "japan": "Asia",
            "china": "Asia",
            "india": "Asia",
            "singapore": "Asia",
            "australia": "Australia",
            "canada": "Canada",
            "brazil": "Brazil",
            "south korea": "South Korea",
            "korea": "South Korea",
            "israel": "Israel",
            "mexico": "Other",
            "argentina": "Other",
            "uae": "Other",
            "global": "global",
        }

        return region_mapping.get(region_name.lower())
