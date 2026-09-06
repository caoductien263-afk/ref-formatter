"""
Tier 5 Adversarial & Empirical Stress Test Suite
Author: Challenger 1 (teamwork_preview_challenger_1)
Target: Streamlit Gemini Reference Formatter (core/gemini_service.py, core/formatter_utils.py, app.py)

Probes:
1. ReDoS / Catastrophic regex backtracking with 100,000+ characters.
2. Extreme length reference lists (1,000+ items, multi-megabyte text).
3. Complex Unicode: Vietnamese diacritics, CJK, Cyrillic, emojis, zero-width spaces, RTL markers.
4. Unusual citation formats: unnumbered APA, roman numerals, bullet variations, mixed delimiters.
5. Markdown code fences with adversarial noise (preceding text, unclosed ticks, quadruple ticks).
6. URLs and DOIs with underscores, parentheses, ampersands, query strings.
7. HTML / XSS sanitization and boundary safety (script tags, img onerror, null bytes).
8. Boundary conditions for all formatter utility functions.
9. Tempfile creation and deterministic cleanup under 6 distinct failure injection points.
"""

import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import time
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.gemini_service import (
    resolve_api_key,
    extract_docx_text,
    extract_guideline_from_file_or_text,
    format_references,
)
from core.formatter_utils import (
    strip_code_fences,
    normalize_markdown_output,
    has_missing_placeholders,
    _markdown_line_to_html,
    generate_word_compatible_html,
)


def make_mock_genai_env(custom_genai=None):
    genai_mock = custom_genai if custom_genai is not None else MagicMock()
    google_mock = MagicMock()
    google_mock.generativeai = genai_mock
    return genai_mock, {"google": google_mock, "google.generativeai": genai_mock}


class TestAdversarialReDoSAndPerformance(unittest.TestCase):
    """Stress test regular expressions against ReDoS and catastrophic backtracking."""

    def test_strip_code_fences_redos_resistance(self):
        """Test strip_code_fences against long unclosed fence prefix (100k chars)."""
        adversarial_input = "```markdown\n" + ("a" * 100000)
        start = time.perf_counter()
        result = strip_code_fences(adversarial_input)
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 0.5, f"strip_code_fences took too long: {elapsed:.3f}s (possible ReDoS)")
        self.assertTrue(len(result) > 0)

    def test_strip_code_fences_multiple_backticks_noise(self):
        """Test strip_code_fences with varying backtick counts and trailing spaces."""
        cases = [
            "````markdown\n[1] Ref\n````",
            "```\n[1] Ref\n```   \t  ",
            "```markdown\r\n[1] Ref\r\n```",
            "`````\n[1] Ref\n`````",
        ]
        for c in cases:
            res = strip_code_fences(c)
            self.assertIn("[1] Ref", res)

    def test_normalize_markdown_redos_resistance(self):
        """Test normalize_markdown_output with 50,000 newlines and whitespace."""
        adversarial_input = ("\n" * 50000) + "[1] Author.\n" + ("\n" * 50000)
        start = time.perf_counter()
        result = normalize_markdown_output(adversarial_input)
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 1.0, f"normalize_markdown_output took too long: {elapsed:.3f}s")
        self.assertEqual(result, "[1] Author.")

    def test_markdown_line_to_html_unclosed_markdown_redos(self):
        """Test _markdown_line_to_html with unclosed asterisks and underscores."""
        adversarial = "**" + ("a" * 50000)
        start = time.perf_counter()
        res = _markdown_line_to_html(adversarial)
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 0.5, f"Backtracking in bold regex: {elapsed:.3f}s")
        self.assertIn("a" * 100, res)

        adversarial_italic = "*" + ("b" * 50000)
        start = time.perf_counter()
        res_italic = _markdown_line_to_html(adversarial_italic)
        elapsed_italic = time.perf_counter() - start
        self.assertLess(elapsed_italic, 0.5, f"Backtracking in italic regex: {elapsed_italic:.3f}s")


class TestAdversarialExtremeInputs(unittest.TestCase):
    """Stress test extreme input sizes, massive token lengths, and high item counts."""

    def test_massive_reference_list_1000_items(self):
        """Test formatting and HTML generation with 1,000 reference entries."""
        items = []
        for i in range(1, 1001):
            items.append(
                f"[{i}] Tác giả thứ {i}, Đồng tác giả {i}. (2024). Tên bài báo nghiên cứu số {i} với độ dài tương đối lớn để kiểm tra bộ nhớ. *Tạp chí Khoa học và Công nghệ Quốc gia*, Tập {i}(Số {i % 12 + 1}), tr. {i * 10}-{i * 10 + 15}. https://doi.org/10.1234/journal.{i}"
            )
        raw_text = "\n".join(items)
        self.assertGreater(len(raw_text), 200000)

        start = time.perf_counter()
        normalized = normalize_markdown_output(raw_text)
        norm_elapsed = time.perf_counter() - start
        self.assertLess(norm_elapsed, 2.0, f"Normalization of 1,000 items took {norm_elapsed:.2f}s")

        self.assertIn("[1] Tác giả", normalized)
        self.assertIn("[1000] Tác giả", normalized)
        self.assertIn("\n\n[500]", normalized)

        start_html = time.perf_counter()
        html_out = generate_word_compatible_html(normalized)
        html_elapsed = time.perf_counter() - start_html
        self.assertLess(html_elapsed, 3.0, f"HTML generation of 1,000 items took {html_elapsed:.2f}s")
        self.assertIn("[1000]", html_out)
        self.assertIn('class="ref-item"', html_out)

    def test_single_extremely_long_citation_line(self):
        """Test citation entry with an unusually long abstract or title (20,000 chars in 1 item)."""
        huge_title = "A" * 20000
        citation = f"[1] Author, A. (2023). {huge_title}. *Journal of Stress Testing*, 1(1), 1-100."
        normalized = normalize_markdown_output(citation)
        html_out = generate_word_compatible_html(normalized)
        self.assertIn("<em>Journal of Stress Testing</em>", html_out)
        self.assertIn(huge_title[:100], html_out)


class TestAdversarialUnicodeAndEncodings(unittest.TestCase):
    """Stress test complex Unicode, Vietnamese diacritics, CJK, emojis, and special spaces."""

    def test_vietnamese_complex_diacritics_in_formatting(self):
        """Test Vietnamese names with full tonemarks and diacritics (Họ, Tên, Tạp chí)."""
        sample = (
            "[1] Nguyễn Đắc Triệu Vũ, Trần Thị Bích Phượng, Hoàng Ngô Tự Lập. (2024). "
            "Nghiên cứu ứng dụng Trí tuệ nhân tạo trong xử lý ngôn ngữ tự nhiên tiếng Việt. "
            "*Tạp chí Nghiên cứu Khoa học & Phát triển Công nghệ Việt Nam*, **15**(4), 89-102. "
            "[Điền ngày/tháng/năm]\n"
            "[2] Đỗ Mai Quỳnh Như, Vũ Đình Trọng Thư. (2023). *Cẩm nang Tra cứu Thư mục*. NXB Đại học Quốc gia."
        )
        normalized = normalize_markdown_output(sample)
        self.assertIn("\n\n[2]", normalized)
        self.assertTrue(has_missing_placeholders(normalized))

        html_out = generate_word_compatible_html(normalized)
        self.assertIn("Nguyễn Đắc Triệu Vũ", html_out)
        self.assertIn("<em>Tạp chí Nghiên cứu Khoa học &amp; Phát triển Công nghệ Việt Nam</em>", html_out)
        self.assertIn("<strong>15</strong>", html_out)
        self.assertIn("background-color: #fff3cd", html_out)

    def test_multilingual_citations_cjk_cyrillic_arabic(self):
        """Test non-Latin alphabets: Japanese, Chinese, Cyrillic, Arabic in citations."""
        sample = (
            "[1] 山田 太郎, 田中 花子. (2022). *自然言語処理の最前線*. 東京大学出版会.\n"
            "[2] Иванов, И. И., Петров, П. П. (2021). *Вестник машиностроения*, 5, 20-30.\n"
            "[3] أحمد, م. (2020). *مجلة الذكاء الاصطناعي*, 3(1), 45-50."
        )
        normalized = normalize_markdown_output(sample)
        self.assertIn("\n\n[2]", normalized)
        self.assertIn("\n\n[3]", normalized)

        html_out = generate_word_compatible_html(normalized)
        self.assertIn("山田 太郎", html_out)
        self.assertIn("Иванов", html_out)
        self.assertIn("أحمد", html_out)
        self.assertIn("<em>自然言語処理の最前線</em>", html_out)

    def test_special_unicode_whitespace_and_zero_width_chars(self):
        """Test zero-width spaces (\u200b), non-breaking spaces (\u00a0), and tabs."""
        sample = "[1]\u00a0Author,\u200b\u00a0A.\u200b (2020).\t*Title*.\n[2]\u00a0Author,\u00a0B. (2021). *Journal*."
        normalized = normalize_markdown_output(sample)
        self.assertIn("[1]", normalized)
        self.assertIn("[2]", normalized)
        html_out = generate_word_compatible_html(normalized)
        self.assertIn("<em>Title</em>", html_out)
        self.assertIn("<em>Journal</em>", html_out)

    def test_emoji_and_symbolic_citations(self):
        """Test presence of emojis or symbolic icons without regex corruption."""
        sample = "[1] 🔬 Researcher, X. (2023). 🚀 *Rocket Science & AI*. 📊 Data Press."
        html_out = generate_word_compatible_html(sample)
        self.assertIn("🔬", html_out)
        self.assertIn("🚀", html_out)
        self.assertIn("<em>Rocket Science &amp; AI</em>", html_out)


class TestAdversarialCitationNumberingAndDelimiters(unittest.TestCase):
    """Stress test unusual citation numbering, bullet styles, and delimiters."""

    def test_parenthesis_numbering(self):
        """Test (1), (2), (3) numbering delimiters."""
        raw = "(1) First citation.\n(2) Second citation.\n(3) Third citation."
        normalized = normalize_markdown_output(raw)
        self.assertIn("(1) First citation.\n\n(2) Second citation.", normalized)
        self.assertIn("(2) Second citation.\n\n(3) Third citation.", normalized)

    def test_bullet_points_various_symbols(self):
        """Test bullets: hyphen '-', asterisk '*', bullet '•'."""
        raw = "- Citation hyphen.\n* Citation asterisk.\n• Citation bullet unicode."
        normalized = normalize_markdown_output(raw)
        self.assertIn("- Citation hyphen.\n\n* Citation asterisk.", normalized)
        self.assertIn("* Citation asterisk.\n\n• Citation bullet unicode.", normalized)

    def test_mixed_delimiters_and_irregular_spacing(self):
        """Test mixed formats: [1], 2., (3), - bullet in single text."""
        raw = "[1] Item one.\n2. Item two.\n(3) Item three.\n- Item four."
        normalized = normalize_markdown_output(raw)
        self.assertIn("[1] Item one.\n\n2. Item two.", normalized)
        self.assertIn("2. Item two.\n\n(3) Item three.", normalized)
        self.assertIn("(3) Item three.\n\n- Item four.", normalized)


class TestAdversarialUrlsAndDois(unittest.TestCase):
    """Stress test complex URLs, DOIs with underscores, parentheses, ampersands, and parameters."""

    def test_doi_with_underscores_in_html(self):
        """Verify underscores in DOIs or URLs do not unintentionally trigger italics."""
        raw = "[1] Author, A. (2020). *Study*. https://doi.org/10.1016/j.jneumeth_2020_05_012"
        html_out = _markdown_line_to_html(raw)
        # Should not convert _2020_ or _05_ into <em> inside a URL
        self.assertIn("https://doi.org/10.1016/j.jneumeth_2020_05_012", html_out)
        self.assertNotIn("<em>2020</em>", html_out)

    def test_markdown_link_with_query_params_and_ampersand(self):
        """Verify markdown links with & and ? parameters are properly escaped and linked."""
        raw = "[1] Dataset: [View Data](https://example.com/api?id=123&format=json&token=xyz_abc)"
        html_out = _markdown_line_to_html(raw)
        self.assertIn('<a href="https://example.com/api?id=123&amp;format=json&amp;token=xyz_abc">View Data</a>', html_out)

    def test_doi_url_with_parentheses(self):
        """Verify DOI containing parentheses like 10.1002/(SICI)1097-0142."""
        raw = "[1] Smith, J. (1998). *Cancer*. https://doi.org/10.1002/(SICI)1097-0142"
        html_out = generate_word_compatible_html(raw)
        self.assertIn("https://doi.org/10.1002/(SICI)1097-0142", html_out)


class TestAdversarialHtmlXssSanitization(unittest.TestCase):
    """Verify HTML escaping prevents script injection or DOM corruption."""

    def test_xss_script_injection_escaped(self):
        """Verify <script> tags are neutralized."""
        malicious = "[1] <script>alert('XSS')</script> Author, A. (2020). *Title*."
        html_out = _markdown_line_to_html(malicious)
        self.assertNotIn("<script>", html_out)
        self.assertIn("&lt;script&gt;alert(&#x27;XSS&#x27;)&lt;/script&gt;", html_out)

    def test_xss_img_onerror_injection_escaped(self):
        """Verify <img src=x onerror=alert(1)> is neutralized via HTML escaping."""
        malicious = '[1] Author <img src="x" onerror="alert(1)">. (2021).'
        html_out = _markdown_line_to_html(malicious)
        self.assertNotIn("<img", html_out)
        self.assertIn("&lt;img", html_out)
        self.assertIn("&gt;", html_out)

    def test_null_byte_handling(self):
        """Verify null bytes in raw input do not crash normalization."""
        raw_with_null = "[1] Author\x00 Name. (2020). *Title*."
        normalized = normalize_markdown_output(raw_with_null)
        html_out = generate_word_compatible_html(normalized)
        self.assertIn("Author", html_out)


class TestAdversarialPlaceholderVariations(unittest.TestCase):
    """Stress test detection of missing placeholder tags."""

    def test_missing_placeholders_variations(self):
        """Test diverse variations of [Điền ...] tag."""
        valid_placeholders = [
            "[Điền ngày/tháng/năm]",
            "[điền ngày/tháng/năm]",
            "[ĐIỀN NGÀY/THÁNG/NĂM]",
            "[Điền số trang]",
            "[Điền DOI]",
            "[Điền tập, số]",
            "[Điền nhà xuất bản]",
            "[Điền tên tác giả]",
            "Text with [Điền thông tin còn thiếu] in middle",
        ]
        for p in valid_placeholders:
            self.assertTrue(has_missing_placeholders(p), f"Failed to detect placeholder: {p}")

    def test_unrelated_brackets_do_not_falsely_trigger(self):
        """Test that normal brackets [1], [in press], [Online], [Editor] do NOT trigger."""
        normal_texts = [
            "[1] Nguyen, A. (2020). [Online]. Available at http://example.com",
            "[2] Smith, J. (in press). [Special Issue]. Journal.",
            "[3] Johnson, K. [Editor]. (2021). *Handbook*.",
            "Normal text without any brackets at all",
        ]
        for t in normal_texts:
            self.assertFalse(has_missing_placeholders(t), f"False positive detection for: {t}")


class TestEphemeralTempfileFailureCleanup(unittest.TestCase):
    """
    Simulate failures at every phase of extract_guideline_from_file_or_text
    to empirically prove that NO temporary files or remote files leak.
    """

    def setUp(self):
        self.mock_genai, self.sys_mods = make_mock_genai_env()

    def test_cleanup_when_upload_file_raises_exception(self):
        """Failure injection 1: genai.upload_file raises network error."""
        self.mock_genai.upload_file.side_effect = ConnectionError("Network unreachable")

        created_files = []
        orig_named_temp = tempfile.NamedTemporaryFile

        def tracking_tempfile(*args, **kwargs):
            tmp = orig_named_temp(*args, **kwargs)
            created_files.append(tmp.name)
            return tmp

        with patch("core.gemini_service.tempfile.NamedTemporaryFile", side_effect=tracking_tempfile):
            with patch.dict("sys.modules", self.sys_mods):
                with self.assertRaises(ConnectionError):
                    extract_guideline_from_file_or_text(
                        api_key="mock-key",
                        file_bytes=b"%PDF-1.4 test bytes",
                        filename="test_paper.pdf",
                    )

        self.assertEqual(len(created_files), 1)
        self.assertFalse(
            os.path.exists(created_files[0]),
            f"Tempfile {created_files[0]} leaked after upload_file exception!"
        )

    def test_cleanup_when_polling_times_out(self):
        """Failure injection 2: File stays PROCESSING until timeout."""
        fake_file = MagicMock()
        fake_file.state.name = "PROCESSING"
        fake_file.name = "files/timeout-test-123"
        self.mock_genai.upload_file.return_value = fake_file
        self.mock_genai.get_file.return_value = fake_file

        created_files = []
        orig_named_temp = tempfile.NamedTemporaryFile

        def tracking_tempfile(*args, **kwargs):
            tmp = orig_named_temp(*args, **kwargs)
            created_files.append(tmp.name)
            return tmp

        # Accelerate time to avoid 60s sleep during test
        with patch("core.gemini_service.tempfile.NamedTemporaryFile", side_effect=tracking_tempfile):
            with patch("core.gemini_service.time.sleep", return_value=None):
                with patch("core.gemini_service.time.time", side_effect=[0, 10, 70, 75]):
                    with patch.dict("sys.modules", self.sys_mods):
                        with self.assertRaises(TimeoutError):
                            extract_guideline_from_file_or_text(
                                api_key="mock-key",
                                file_bytes=b"%PDF-1.4 test bytes",
                                filename="timeout_test.pdf",
                            )

        # Verify local tempfile deleted
        self.assertEqual(len(created_files), 1)
        self.assertFalse(os.path.exists(created_files[0]), "Local tempfile leaked on TimeoutError!")
        # Verify remote gemini file deleted
        self.mock_genai.delete_file.assert_called_once_with("files/timeout-test-123")

    def test_cleanup_when_file_state_failed(self):
        """Failure injection 3: Gemini File API returns state=FAILED."""
        fake_file = MagicMock()
        fake_file.state.name = "FAILED"
        fake_file.name = "files/failed-state-456"
        self.mock_genai.upload_file.return_value = fake_file

        created_files = []
        orig_named_temp = tempfile.NamedTemporaryFile

        def tracking_tempfile(*args, **kwargs):
            tmp = orig_named_temp(*args, **kwargs)
            created_files.append(tmp.name)
            return tmp

        with patch("core.gemini_service.tempfile.NamedTemporaryFile", side_effect=tracking_tempfile):
            with patch.dict("sys.modules", self.sys_mods):
                with self.assertRaises(RuntimeError):
                    extract_guideline_from_file_or_text(
                        api_key="mock-key",
                        file_bytes=b"%PDF-1.4 test bytes",
                        filename="fail_state.pdf",
                    )

        self.assertEqual(len(created_files), 1)
        self.assertFalse(os.path.exists(created_files[0]), "Local tempfile leaked on FAILED state!")
        self.mock_genai.delete_file.assert_called_once_with("files/failed-state-456")

    def test_cleanup_when_generate_content_fails(self):
        """Failure injection 4: Model generate_content throws 500 error."""
        fake_file = MagicMock()
        fake_file.state.name = "ACTIVE"
        fake_file.name = "files/gen-fail-789"
        self.mock_genai.upload_file.return_value = fake_file

        mock_model = MagicMock()
        mock_model.generate_content.side_effect = RuntimeError("Internal Gemini Server Error 500")
        self.mock_genai.GenerativeModel.return_value = mock_model

        created_files = []
        orig_named_temp = tempfile.NamedTemporaryFile

        def tracking_tempfile(*args, **kwargs):
            tmp = orig_named_temp(*args, **kwargs)
            created_files.append(tmp.name)
            return tmp

        with patch("core.gemini_service.tempfile.NamedTemporaryFile", side_effect=tracking_tempfile):
            with patch.dict("sys.modules", self.sys_mods):
                with self.assertRaises(RuntimeError):
                    extract_guideline_from_file_or_text(
                        api_key="mock-key",
                        file_bytes=b"%PDF-1.4 test bytes",
                        filename="gen_fail.pdf",
                    )

        self.assertEqual(len(created_files), 1)
        self.assertFalse(os.path.exists(created_files[0]), "Local tempfile leaked on generate_content error!")
        self.mock_genai.delete_file.assert_called_once_with("files/gen-fail-789")

    def test_cleanup_resilience_when_delete_file_itself_raises(self):
        """Failure injection 5: genai.delete_file raises exception (e.g. already expired)."""
        fake_file = MagicMock()
        fake_file.state.name = "ACTIVE"
        fake_file.name = "files/delete-err-999"
        self.mock_genai.upload_file.return_value = fake_file
        self.mock_genai.delete_file.side_effect = Exception("File already deleted or 404")

        mock_model = MagicMock()
        mock_model.generate_content.return_value.text = "Success summary"
        self.mock_genai.GenerativeModel.return_value = mock_model

        created_files = []
        orig_named_temp = tempfile.NamedTemporaryFile

        def tracking_tempfile(*args, **kwargs):
            tmp = orig_named_temp(*args, **kwargs)
            created_files.append(tmp.name)
            return tmp

        with patch("core.gemini_service.tempfile.NamedTemporaryFile", side_effect=tracking_tempfile):
            with patch.dict("sys.modules", self.sys_mods):
                result = extract_guideline_from_file_or_text(
                    api_key="mock-key",
                    file_bytes=b"%PDF-1.4 test bytes",
                    filename="delete_err.pdf",
                )

        # Even though delete_file raised, function succeeded and local tempfile was removed
        self.assertEqual(result, "Success summary")
        self.assertEqual(len(created_files), 1)
        self.assertFalse(os.path.exists(created_files[0]), "Local tempfile leaked when delete_file failed!")

    def test_corrupted_docx_bytes_fails_cleanly(self):
        """Failure injection 6: Corrupted .docx buffer (not valid zip/XML)."""
        corrupted_bytes = b"NOT_A_VALID_ZIP_HEADER_JUST_GARBAGE"
        with self.assertRaises(Exception):
            extract_docx_text(corrupted_bytes)


class TestAdversarialBoundaryEdgeCases(unittest.TestCase):
    """Stress test boundary edge cases and documented behavioral limitations."""

    def test_strip_code_fences_with_surrounding_dialogue(self):
        """
        Documented edge case: When LLM outputs conversational prefixes/suffixes
        outside the code fences, strip_code_fences does not strip them.
        """
        raw = "Here are references:\n```markdown\n[1] Ref 1\n```\nHope it helps!"
        res = strip_code_fences(raw)
        # Verify boundary behavior: exact string returned because anchors ^ and $ fail
        self.assertEqual(res, raw)

    def test_strip_code_fences_unclosed_fence(self):
        """
        Documented edge case: When an LLM output is truncated and lacks closing ```,
        strip_code_fences leaves the opening fence intact.
        """
        raw = "```markdown\n[1] Incomplete citation list"
        res = strip_code_fences(raw)
        self.assertEqual(res, raw)

    def test_extract_guideline_file_bytes_without_filename_boundary(self):
        """
        Documented API boundary: Passing file_bytes without filename skips file processing
        because the extension cannot be inferred without filename.
        """
        mock_genai, sys_mods = make_mock_genai_env()
        mock_model = MagicMock()
        mock_model.generate_content.return_value.text = "Result"
        mock_genai.GenerativeModel.return_value = mock_model

        with patch.dict("sys.modules", sys_mods):
            res = extract_guideline_from_file_or_text(
                api_key="mock-key",
                file_bytes=b"%PDF-1.4...",
                filename=None,
            )
            # Verify it generated content with prompt only
            contents = mock_model.generate_content.call_args[0][0]
            self.assertEqual(len(contents), 1)  # Only the prompt, file skipped

    def test_multiple_italic_segments_in_single_entry(self):
        """Test multiple distinct italic spans in one citation line."""
        line = "[1] Author. *Journal of AI*, *12*(3), *Supplement A*, 45-50."
        html_out = _markdown_line_to_html(line)
        self.assertIn("<em>Journal of AI</em>", html_out)
        self.assertIn("<em>12</em>", html_out)
        self.assertIn("<em>Supplement A</em>", html_out)

    def test_none_and_empty_inputs_safety_across_all_utils(self):
        """Verify all utility functions handle empty/None safely without unhandled exceptions."""
        self.assertEqual(strip_code_fences(""), "")
        self.assertEqual(strip_code_fences(None), "")  # type: ignore[arg-type]
        self.assertEqual(normalize_markdown_output(""), "")
        self.assertEqual(normalize_markdown_output(None), "")  # type: ignore[arg-type]
        self.assertFalse(has_missing_placeholders(""))
        self.assertFalse(has_missing_placeholders(None))  # type: ignore[arg-type]
        self.assertEqual(_markdown_line_to_html(""), "")
        empty_html = generate_word_compatible_html("")
        self.assertIn("<!DOCTYPE html>", empty_html)


if __name__ == "__main__":
    unittest.main()
