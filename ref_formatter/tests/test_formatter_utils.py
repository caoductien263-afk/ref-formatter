"""
Tier 1 Tests: Formatter Utilities (F13, F14, F15, F16)
Validates markdown normalization, code fence stripping, rich-text tags,
placeholder detection, and Word-compatible HTML export.
"""

import unittest
import re
import html
from core.formatter_utils import (
    strip_code_fences,
    normalize_markdown_output,
    has_missing_placeholders,
    _markdown_line_to_html,
    generate_word_compatible_html,
)


class TestMarkdownNormalizationF13(unittest.TestCase):
    """F13: Markdown Output Normalization (Fences & Linebreaks)."""

    def test_strip_code_fences_with_markdown_tag(self):
        """Test stripping of enclosing ```markdown ... ``` fences."""
        raw = "```markdown\n[1] Author A. *Title*. Journal, 2020.\n[2] Author B. *Book*. 2021.\n```"
        result = strip_code_fences(raw)
        self.assertFalse(result.startswith("```"))
        self.assertFalse(result.endswith("```"))
        self.assertIn("[1] Author A", result)
        self.assertIn("[2] Author B", result)

    def test_strip_code_fences_with_plain_ticks(self):
        """Test stripping of enclosing ``` ... ``` fences without language tag."""
        raw = "```\n[1] Smith J. (2020). *Nature*, 12, 34-45.\n```"
        result = strip_code_fences(raw)
        self.assertFalse(result.startswith("```"))
        self.assertFalse(result.endswith("```"))
        self.assertIn("[1] Smith J.", result)

    def test_strip_code_fences_unfenced_input_preserved(self):
        """Test that plain text without fences is returned intact."""
        raw = "[1] Nguyen V. A. (2022). *AI Research*, 10, 100-110."
        result = strip_code_fences(raw)
        self.assertEqual(result, raw)

    def test_normalize_linebreaks_between_bracket_references(self):
        """Test conversion of single newline between [1] and [2] to double newlines."""
        raw = "[1] First citation item.\n[2] Second citation item.\n[3] Third citation item."
        normalized = normalize_markdown_output(raw)
        self.assertIn("[1] First citation item.\n\n[2] Second citation item.", normalized)
        self.assertIn("[2] Second citation item.\n\n[3] Third citation item.", normalized)

    def test_normalize_linebreaks_between_dot_numbered_references(self):
        """Test conversion of single newline between 1. and 2. to double newlines."""
        raw = "1. Citation one details.\n2. Citation two details.\n3. Citation three details."
        normalized = normalize_markdown_output(raw)
        self.assertIn("1. Citation one details.\n\n2. Citation two details.", normalized)
        self.assertIn("2. Citation two details.\n\n3. Citation three details.", normalized)

    def test_normalize_crlf_and_collapse_excessive_newlines(self):
        """Test normalization of Windows CRLF line endings and collapsing of 3+ newlines."""
        raw = "[1] Item 1.\r\n\r\n\r\n\r\n[2] Item 2.\r\n[3] Item 3."
        normalized = normalize_markdown_output(raw)
        self.assertNotIn("\r", normalized)
        self.assertNotIn("\n\n\n", normalized)
        self.assertIn("[1] Item 1.\n\n[2] Item 2.", normalized)
        self.assertIn("[2] Item 2.\n\n[3] Item 3.", normalized)

    def test_normalize_empty_and_whitespace_input(self):
        """Test that empty or whitespace-only input returns an empty string cleanly."""
        self.assertEqual(normalize_markdown_output(""), "")
        self.assertEqual(normalize_markdown_output("   \n\t  "), "")


class TestRichTextWordCopyPasteF14(unittest.TestCase):
    """F14: Rich-Text Word Copy-Paste Formatting."""

    def test_markdown_line_to_html_italics(self):
        """Test conversion of markdown asterisks *text* to <em>text</em> for Word italics."""
        line = "Nguyen, A. (2020). *Journal of Computer Science*, 15(2), 10-20."
        html_out = _markdown_line_to_html(line)
        self.assertIn("<em>Journal of Computer Science</em>", html_out)

    def test_markdown_line_to_html_bold(self):
        """Test conversion of markdown **text** to <strong>text</strong> for Word bolding."""
        line = "**[1]** Le, B. (2021). **Machine Learning Today**."
        html_out = _markdown_line_to_html(line)
        self.assertIn("<strong>[1]</strong>", html_out)
        self.assertIn("<strong>Machine Learning Today</strong>", html_out)

    def test_markdown_line_to_html_links(self):
        """Test conversion of markdown [label](url) to HTML <a> tag."""
        line = "Available at: [https://doi.org/10.1000/182](https://doi.org/10.1000/182)"
        html_out = _markdown_line_to_html(line)
        self.assertIn('<a href="https://doi.org/10.1000/182">https://doi.org/10.1000/182</a>', html_out)

    def test_markdown_line_to_html_inline_code(self):
        """Test conversion of inline `code` to <code> tags."""
        line = "Algorithm details in `ref_module.py`."
        html_out = _markdown_line_to_html(line)
        self.assertIn("<code>ref_module.py</code>", html_out)

    def test_markdown_line_to_html_special_character_escaping(self):
        """Test HTML escaping of &, <, > to prevent malformed DOM."""
        line = "Johnson & Johnson <Research> Department."
        html_out = _markdown_line_to_html(line)
        self.assertIn("Johnson &amp; Johnson", html_out)
        self.assertIn("&lt;Research&gt;", html_out)

    def test_markdown_line_to_html_combined_formatting(self):
        """Test line combining bold index, italic journal, and regular bibliographic text."""
        line = "**[1]** Tran, V. (2023). Deep neural networks. *Nature Intelligence*, **5**(1), 1-15."
        html_out = _markdown_line_to_html(line)
        self.assertIn("<strong>[1]</strong>", html_out)
        self.assertIn("<em>Nature Intelligence</em>", html_out)
        self.assertIn("<strong>5</strong>", html_out)


class TestMissingPlaceholderWarningF15(unittest.TestCase):
    """F15: Missing Data Placeholder Detection ([Điền ngày/tháng/năm])."""

    def test_detect_standard_vietnamese_date_placeholder(self):
        """Test detection of exact [Điền ngày/tháng/năm] tag."""
        text = "[1] Pham, H. ([Điền ngày/tháng/năm]). *Handbook of Data Science*."
        self.assertTrue(has_missing_placeholders(text))

    def test_detect_page_number_placeholder(self):
        """Test detection of [Điền thiếu số trang] or [Điền số trang]."""
        text = "[1] Pham, H. (2022). *AI Journal*, 12, [Điền số trang]."
        self.assertTrue(has_missing_placeholders(text))

    def test_detect_publisher_and_doi_placeholders(self):
        """Test detection of [Điền nhà xuất bản] and [Điền DOI]."""
        text1 = "[1] Pham, H. (2020). *Book Title*, [Điền nhà xuất bản]."
        text2 = "[2] Le, K. (2021). *Paper Title*, [Điền DOI]."
        self.assertTrue(has_missing_placeholders(text1))
        self.assertTrue(has_missing_placeholders(text2))

    def test_return_false_when_all_metadata_present(self):
        """Test that fully specified citations return False."""
        complete_text = (
            "[1] Nguyen, V. A. (2020). Machine Learning in Healthcare. "
            "*Journal of Medical Systems*, 44(6), 112-120. https://doi.org/10.1007/s10916-020-01582-7\n\n"
            "[2] Tran, T. B. (2019). *Deep Learning Handbook*. Science Press."
        )
        self.assertFalse(has_missing_placeholders(complete_text))

    def test_case_insensitive_placeholder_matching(self):
        """Test detection with lowercase or mixed case [điền ngày/tháng/năm]."""
        text = "[1] Author, A. ([điền ngày/tháng/năm]). *Sample Journal*."
        self.assertTrue(has_missing_placeholders(text))

    def test_empty_or_none_input(self):
        """Test that empty string or None safely returns False without raising exceptions."""
        self.assertFalse(has_missing_placeholders(""))
        self.assertFalse(has_missing_placeholders(None))  # type: ignore[arg-type]


class TestWordCompatibleHtmlExportF16(unittest.TestCase):
    """F16: HTML File Export for Direct Word Opening."""

    def setUp(self):
        self.sample_markdown = (
            "# Danh mục tài liệu tham khảo\n\n"
            "[1] Nguyen, V. A. (2020). Neural networks. *Journal of AI*, **10**(2), 50-60.\n\n"
            "[2] Le, T. C. ([Điền ngày/tháng/năm]). *Robotics Guide*. Publisher."
        )
        self.html = generate_word_compatible_html(self.sample_markdown)

    def test_html_document_structure(self):
        """Test that generated HTML has valid DOCTYPE, html, head, and body tags."""
        self.assertTrue(self.html.startswith("<!DOCTYPE html>"))
        self.assertIn("<html", self.html)
        self.assertIn("<head>", self.html)
        self.assertIn("<meta charset=\"utf-8\">", self.html)
        self.assertIn("<body>", self.html)
        self.assertIn("</html>", self.html)

    def test_mso_word_xml_namespace_and_conditional_comments(self):
        """Test Microsoft Office Word XML namespace and WordDocument view configuration."""
        self.assertIn("xmlns:w=\"urn:schemas-microsoft-com:office:word\"", self.html)
        self.assertIn("<w:WordDocument>", self.html)
        self.assertIn("<w:View>Print</w:View>", self.html)

    def test_academic_hanging_indent_css(self):
        """Test that CSS specifies 12pt Times New Roman and hanging indent (-0.5in text-indent)."""
        self.assertIn("font-family: 'Times New Roman'", self.html)
        self.assertIn("font-size: 12pt", self.html)
        self.assertIn("line-height: 1.5", self.html)
        self.assertIn("text-indent: -0.5in", self.html)
        self.assertIn("margin-left: 0.5in", self.html)

    def test_paragraph_and_heading_conversion(self):
        """Test that markdown header becomes <h1> and references become <p class=\"ref-item\">."""
        self.assertIn("<h1>Danh mục tài liệu tham khảo</h1>", self.html)
        self.assertIn('<p class="ref-item">', self.html)
        self.assertIn("<em>Journal of AI</em>", self.html)
        self.assertIn("<strong>10</strong>", self.html)

    def test_missing_placeholder_visual_styling(self):
        """Test that [Điền ...] tags receive distinctive visual badge highlighting in HTML."""
        self.assertIn("background-color: #fff3cd", self.html)
        self.assertIn("[Điền ngày/tháng/năm]", self.html)

    def test_empty_input_produces_valid_skeleton(self):
        """Test that empty markdown input still produces valid HTML container."""
        empty_html = generate_word_compatible_html("")
        self.assertIn("<!DOCTYPE html>", empty_html)
        self.assertIn("<body>", empty_html)
        self.assertIn("</body>", empty_html)


if __name__ == "__main__":
    unittest.main()
