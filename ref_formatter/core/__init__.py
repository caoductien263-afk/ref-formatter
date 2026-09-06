"""
Core package for Streamlit Gemini Reference Formatter.
Provides Gemini API integration, multimodal file processing,
and formatting utilities for academic citations.
"""

from core.gemini_service import (
    resolve_api_key,
    extract_guideline_from_file_or_text,
    format_references,
)
from core.formatter_utils import (
    normalize_markdown_output,
    has_missing_placeholders,
    generate_word_compatible_html,
)

__all__ = [
    "resolve_api_key",
    "extract_guideline_from_file_or_text",
    "format_references",
    "normalize_markdown_output",
    "has_missing_placeholders",
    "generate_word_compatible_html",
]
