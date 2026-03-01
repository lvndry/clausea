"""
Document Analysis Modules

This package contains specialized analyzers for legal document processing,
split from the monolithic DocumentAnalyzer class for better maintainability.
"""

from .date_extractor import DateExtractor
from .document_classifier import DocumentClassifier
from .locale_analyzer import LocaleAnalyzer
from .region_detector import RegionDetector

__all__ = [
    "DateExtractor",
    "DocumentClassifier",
    "LocaleAnalyzer",
    "RegionDetector",
]
