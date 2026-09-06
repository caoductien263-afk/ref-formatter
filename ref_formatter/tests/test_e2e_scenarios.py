"""
Tier 2, 3, and 4 Tests: Boundary Cases, Pairwise Combinations & Real-World Scenarios
Tests edge conditions, cross-module interactions, and end-to-end academic reference workflows.
"""

import unittest
from unittest.mock import patch, MagicMock
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.gemini_service import (
    resolve_api_key,
    extract_guideline_from_file_or_text,
    format_references,
    extract_docx_text,
)
from core.formatter_utils import (
    normalize_markdown_output,
    has_missing_placeholders,
    generate_word_compatible_html,
    strip_code_fences,
)


def make_mock_genai_env(custom_genai=None):
    """
    Creates mock google and google.generativeai modules for sys.modules injection.
    Ensures tests run deterministically in any offline or isolated environment.
    """
    genai_mock = custom_genai if custom_genai is not None else MagicMock()
    google_mock = MagicMock()
    google_mock.generativeai = genai_mock
    return genai_mock, {"google": google_mock, "google.generativeai": genai_mock}


# ==============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ==============================================================================
class TestTier2BoundaryAndCornerCases(unittest.TestCase):
    """Tier 2: Boundary, stress, error recovery, and corner-case tests."""

    def test_b1_empty_and_whitespace_only_inputs(self):
        """B1: Empty text, whitespace, newline-only inputs in formatting and normalization."""
        self.assertEqual(normalize_markdown_output(""), "")
        self.assertEqual(normalize_markdown_output("   \n\n\t  "), "")
        self.assertFalse(has_missing_placeholders(""))
        self.assertFalse(has_missing_placeholders("   \t  "))
        with self.assertRaises(ValueError):
            format_references("api-key", "valid summary", "   \n\t  ")

    def test_b2_extreme_size_large_reference_volume(self):
        """B2: Stress test with 10,000+ characters and 100+ references."""
        large_ref_list = []
        for i in range(1, 120):
            large_ref_list.append(
                f"[{i}] Author {i}, Coauthor {i}. (202{i%5}). Title of paper {i}. "
                f"*Journal of Testing and Scalability*, {i}({i%4+1}), {i*10}-{i*10+15}."
            )
        raw_text = "\n".join(large_ref_list)
        self.assertGreater(len(raw_text), 10000)

        normalized = normalize_markdown_output(raw_text)
        # Verify double newlines are enforced throughout
        self.assertIn("[10] Author 10", normalized)
        self.assertIn("[100] Author 100", normalized)
        self.assertIn("\n\n[50]", normalized)

        # Generate HTML from 10k+ character document
        html_doc = generate_word_compatible_html(normalized)
        self.assertIn("<p class=\"ref-item\">", html_doc)
        self.assertIn("[119]", html_doc)

    def test_b3_complex_filenames_multiple_periods_and_unicode(self):
        """B3: File handling with multiple periods, spaces, and Unicode Vietnamese characters."""
        filenames = [
            "quy_dinh.tap_chi.v2.final.pdf",
            "huong_dan_trich_dan_2024 (1).docx",
            "Báo cáo khoa học & Kỷ yếu.pdf",
        ]
        mock_genai, sys_mods = make_mock_genai_env()
        fake_model = MagicMock()
        fake_model.generate_content.return_value.text = "Analysis complete"
        mock_genai.GenerativeModel.return_value = fake_model
        fake_file = MagicMock()
        fake_file.state.name = "ACTIVE"
        fake_file.name = "files/unicode-test"
        mock_genai.upload_file.return_value = fake_file

        mock_docx = MagicMock()
        mock_doc = MagicMock()
        mock_doc.paragraphs = [MagicMock(text="Sample docx text")]
        mock_doc.tables = []
        mock_docx.Document.return_value = mock_doc
        sys_mods["docx"] = mock_docx

        with patch.dict("sys.modules", sys_mods):
            for fname in filenames:
                result = extract_guideline_from_file_or_text(
                    api_key="test-key",
                    file_bytes=b"%PDF-1.5 test" if fname.endswith(".pdf") else b"PK\x03\x04docx",
                    filename=fname,
                )
                self.assertEqual(result, "Analysis complete")

    def test_b4_corrupted_file_bytes_handling(self):
        """B4: Corrupted docx bytes raise or handle gracefully."""
        mock_docx = MagicMock()
        mock_docx.Document.side_effect = Exception("File is not a zip file or corrupt docx")
        with patch.dict("sys.modules", {"docx": mock_docx}):
            with self.assertRaises(Exception):
                extract_docx_text(b"not-a-valid-zip-buffer")

    def test_b5_api_error_handling_quota_429_and_invalid_arg_400(self):
        """B5: Error handling when Gemini API raises 400 Invalid Argument or 429 Quota."""
        mock_genai, sys_mods = make_mock_genai_env()
        mock_genai.GenerativeModel.return_value.generate_content.side_effect = RuntimeError(
            "429 Quota exceeded: Resource has been exhausted"
        )
        with patch.dict("sys.modules", sys_mods):
            with self.assertRaises(RuntimeError) as ctx:
                format_references("test-key", "summary", "1. Ref")
            self.assertIn("429", str(ctx.exception))

    def test_b6_mixed_and_unnumbered_citation_styles(self):
        """B6: Handling raw input with mixed numbering, unnumbered bullet points, and bare URLs."""
        raw_mixed = (
            "- First unnumbered bullet citation\n"
            "* Second asterisk bullet citation\n"
            "3. Numbered with dot\n"
            "[4] Numbered with bracket\n"
            "https://example.com/raw-url-citation"
        )
        normalized = normalize_markdown_output(raw_mixed)
        self.assertTrue(normalized.startswith("- First"))
        self.assertIn("\n\n* Second", normalized)
        self.assertIn("\n\n3.", normalized)
        self.assertIn("\n\n[4]", normalized)


# ==============================================================================
# TIER 3: CROSS-FEATURE COMBINATIONS (PAIRWISE COVERAGE)
# ==============================================================================
class TestTier3CrossFeatureCombinations(unittest.TestCase):
    """Tier 3: Pairwise interactions across service, wizard, and formatting."""

    def test_pair_1_pdf_upload_and_guideline_edit_and_missing_date(self):
        """
        Pair 1: Upload PDF -> Review and Edit guideline in Step 2 ->
        Format citations with missing publication year -> Detect [Điền ngày/tháng/năm].
        """
        mock_genai, sys_mods = make_mock_genai_env()
        mock_genai.GenerativeModel.return_value.generate_content.return_value.text = (
            "[1] Nguyen, V. ([Điền ngày/tháng/năm]). *Journal of AI*, 10, 20-30."
        )
        fake_file = MagicMock()
        fake_file.state.name = "ACTIVE"
        fake_file.name = "files/pair-1"
        mock_genai.upload_file.return_value = fake_file

        with patch.dict("sys.modules", sys_mods):
            # Step 1: PDF guideline extraction
            pdf_bytes = b"%PDF-1.5 test guide"
            extracted_summary = extract_guideline_from_file_or_text(
                api_key="valid-key",
                file_bytes=pdf_bytes,
                filename="rules.pdf",
            )
            # Step 2: User tweaks summary
            tweaked_summary = extracted_summary + "\nLưu ý: Đánh dấu [Điền ngày/tháng/năm] nếu thiếu năm."
            
            # Step 3: Formatting with raw refs missing year
            raw_input = "Nguyen Van, Journal of AI, vol 10, pages 20-30 (no year)"
            result = format_references("valid-key", tweaked_summary, raw_input)
            normalized = normalize_markdown_output(result)

            # Verification
            self.assertTrue(has_missing_placeholders(normalized))
            self.assertIn("[Điền ngày/tháng/năm]", normalized)
            self.assertIn("*Journal of AI*", normalized)

    def test_pair_2_docx_upload_and_skip_edit_and_ieee_formatting(self):
        """
        Pair 2: Upload DOCX -> Approve directly -> Format IEEE numbered style -> HTML export.
        """
        mock_genai, sys_mods = make_mock_genai_env()
        mock_genai.GenerativeModel.return_value.generate_content.return_value.text = (
            "```markdown\n"
            "[1] J. K. Author, \"Title of paper,\" *IEEE Trans. Autom. Control*, vol. 45, no. 1, pp. 10-20, Jan. 2020.\n"
            "[2] R. E. Researcher, *Book Title*, 2nd ed. New York: Academic Press, 2019.\n"
            "```"
        )
        mock_docx = MagicMock()
        mock_doc = MagicMock()
        mock_doc.paragraphs = [MagicMock(text="IEEE Reference Guidelines: Numbered [1], [2]")]
        mock_doc.tables = []
        mock_docx.Document.return_value = mock_doc
        sys_mods["docx"] = mock_docx

        with patch.dict("sys.modules", sys_mods):
            # Step 1: DOCX extraction
            summary = extract_guideline_from_file_or_text(
                api_key="valid-key",
                file_bytes=b"PK\x03\x04docx",
                filename="ieee_style.docx",
            )
            # Step 2: Direct approval
            approved_summary = summary
            # Step 3: Format & Export
            raw = "1. Author J.K., Title of paper, IEEE TAC 2020\n2. Researcher R.E., Book Title 2019"
            formatted = format_references("valid-key", approved_summary, raw)
            normalized = normalize_markdown_output(formatted)
            
            # Verify fences stripped and IEEE bracket items separated
            self.assertFalse(normalized.startswith("```"))
            self.assertIn("[1] J. K. Author", normalized)
            self.assertIn("\n\n[2] R. E. Researcher", normalized)
            
            # Export to HTML
            html_out = generate_word_compatible_html(normalized)
            self.assertIn("IEEE Trans. Autom. Control", html_out)
            self.assertIn("class=\"ref-item\"", html_out)

    def test_pair_3_paste_text_and_back_forth_navigation_and_apa_format(self):
        """
        Pair 3: Paste text guideline -> Move to Step 2 -> Return to Step 1 to add detail ->
        Move to Step 3 -> Return to Step 2 -> Proceed back to Step 3 and format APA.
        """
        mock_genai, sys_mods = make_mock_genai_env()
        mock_genai.GenerativeModel.return_value.generate_content.return_value.text = (
            "Smith, J. D. (2021). Cognitive science insights. *American Psychologist*, 76(3), 450-462."
        )

        # Wizard state simulation
        state = {
            "step": 1,
            "guideline_text": "APA 7th standard format",
            "guideline_summary": "",
            "raw_refs": "Smith J.D., Cognitive science insights, 2021",
            "formatted_refs": "",
        }

        # Step 1 -> 2
        state["step"] = 2
        state["guideline_summary"] = "APA 7th Summary"

        # Back to 1 to refine guideline
        state["step"] = 1
        state["guideline_text"] += "\nRule: Italicize journal title and volume number."

        # Back to 2
        state["step"] = 2
        state["guideline_summary"] = "APA 7th Updated Summary with Italics"

        # Forward to 3
        state["step"] = 3
        self.assertEqual(state["raw_refs"], "Smith J.D., Cognitive science insights, 2021")

        # Back to 2
        state["step"] = 2
        # Back to 3
        state["step"] = 3

        with patch.dict("sys.modules", sys_mods):
            res = format_references("key", state["guideline_summary"], state["raw_refs"])
            normalized = normalize_markdown_output(res)
            state["formatted_refs"] = normalized

        self.assertIn("*American Psychologist*", state["formatted_refs"])
        self.assertEqual(state["step"], 3)

    def test_pair_4_env_api_key_and_pdf_network_error_cleanup(self):
        """
        Pair 4: API key resolved from os.environ -> PDF upload throws network error ->
        Verify API key resolved correctly and temporary file cleaned up without leak.
        """
        os.environ["GEMINI_API_KEY"] = "auto-resolved-env-key-99"
        try:
            resolved_key = resolve_api_key(None)
            self.assertEqual(resolved_key, "auto-resolved-env-key-99")

            mock_genai, sys_mods = make_mock_genai_env()
            mock_genai.upload_file.side_effect = ConnectionResetError("Connection reset by peer")

            created_files = []
            orig_named_temp = __import__("tempfile").NamedTemporaryFile

            def track_temp(*args, **kwargs):
                t = orig_named_temp(*args, **kwargs)
                created_files.append(t.name)
                return t

            with patch("tempfile.NamedTemporaryFile", side_effect=track_temp):
                with patch.dict("sys.modules", sys_mods):
                    with self.assertRaises(ConnectionResetError):
                        extract_guideline_from_file_or_text(
                            api_key=resolved_key,
                            file_bytes=b"%PDF-1.5 test",
                            filename="network_fail.pdf",
                        )

            # Ensure all temporary files were removed
            for tf in created_files:
                self.assertFalse(os.path.exists(tf), f"Leaked file: {tf}")
        finally:
            if "GEMINI_API_KEY" in os.environ:
                del os.environ["GEMINI_API_KEY"]

    def test_pair_5_reset_in_step_3_followed_by_fresh_docx_guideline(self):
        """
        Pair 5: Wizard at Step 3 with completed work -> Click Reset ->
        Start fresh run with Word docx file in Step 1.
        """
        state = {
            "step": 3,
            "guideline_text": "Old text",
            "guideline_summary": "Old summary",
            "raw_refs": "Old refs",
            "formatted_refs": "Old formatted",
            "file_info": {"name": "old.pdf"},
        }
        # Reset action
        state["step"] = 1
        state["guideline_text"] = ""
        state["guideline_summary"] = ""
        state["raw_refs"] = ""
        state["formatted_refs"] = ""
        state["file_info"] = None

        self.assertEqual(state["step"], 1)
        self.assertEqual(state["guideline_summary"], "")

        # Fresh DOCX upload
        mock_genai, sys_mods = make_mock_genai_env()
        mock_genai.GenerativeModel.return_value.generate_content.return_value.text = "Fresh DOCX Rules"
        mock_docx = MagicMock()
        mock_doc = MagicMock()
        mock_doc.paragraphs = [MagicMock(text="Fresh Springer Rules")]
        mock_doc.tables = []
        mock_docx.Document.return_value = mock_doc
        sys_mods["docx"] = mock_docx

        with patch.dict("sys.modules", sys_mods):
            fresh_summary = extract_guideline_from_file_or_text(
                api_key="valid-key",
                file_bytes=b"PK\x03\x04fresh",
                filename="springer.docx",
            )
            state["guideline_summary"] = fresh_summary
            state["step"] = 2

        self.assertEqual(state["step"], 2)
        self.assertEqual(state["guideline_summary"], "Fresh DOCX Rules")


# ==============================================================================
# TIER 4: REAL-WORLD APPLICATION SCENARIOS
# ==============================================================================
class TestTier4RealWorldScenarios(unittest.TestCase):
    """Tier 4: End-to-end real-world user workflows."""

    def test_scenario_1_apa_7th_journal_guidelines_and_raw_citations(self):
        """
        Scenario 1: Standard APA 7th Journal Article Guidelines + Raw Citations.
        Exercises: F6, F7, F8, F10, F11, F13, F14.
        """
        apa_guidelines = """
        Quy định trích dẫn APA 7th Edition:
        - Tạp chí: Tác giả (Năm). Tên bài báo. Tên Tạp Chí in nghiêng, Tập(Số), Trang-Trang. DOI.
        - Sắp xếp: Giữ nguyên thứ tự danh sách.
        - In nghiêng: Tên tạp chí và số tập in nghiêng.
        """
        raw_citations = """
        1. Grady JS, Her M, Moreno G, Perez C, Yelinek J. Emotions in storybooks. Dev Psychol 2019, 55(2), 207-217. https://doi.org/10.1037/dev0000647
        2. Jerrentrup A, Mueller T, Glowalla U, et al. Teaching medicine with AI. BMC Med Educ 2018, 18, Article 100.
        """
        expected_llm_response = (
            "```markdown\n"
            "[1] Grady, J. S., Her, M., Moreno, G., Perez, C., & Yelinek, J. (2019). Emotions in storybooks: A comparison of storybooks that represent ethnic and racial groups in the United States. *Developmental Psychology*, *55*(2), 207–217. https://doi.org/10.1037/dev0000647\n\n"
            "[2] Jerrentrup, A., Mueller, T., Glowalla, U., et al. (2018). Teaching medicine with AI. *BMC Medical Education*, *18*, 100.\n"
            "```"
        )
        mock_genai, sys_mods = make_mock_genai_env()
        mock_genai.GenerativeModel.return_value.generate_content.return_value.text = expected_llm_response

        with patch.dict("sys.modules", sys_mods):
            # 1. Guideline extraction
            summary = extract_guideline_from_file_or_text("api-key", text=apa_guidelines)
            # 2. Reference formatting
            formatted = format_references("api-key", summary, raw_citations)
            # 3. Output normalization
            cleaned = normalize_markdown_output(formatted)

        self.assertFalse(cleaned.startswith("```"))
        self.assertIn("*Developmental Psychology*", cleaned)
        self.assertIn("\n\n[2] Jerrentrup", cleaned)
        self.assertFalse(has_missing_placeholders(cleaned))

        # 4. Word HTML export
        html_export = generate_word_compatible_html(cleaned)
        self.assertIn("<em>Developmental Psychology</em>", html_export)
        self.assertIn("class=\"ref-item\"", html_export)

    def test_scenario_2_ieee_numbered_guideline_with_missing_dates(self):
        """
        Scenario 2: IEEE Numbered Guidelines with Missing Publication Years / Dates.
        Exercises: F6, F7, F13, F14, F15.
        """
        ieee_rules = "IEEE Standard: [1] A. Author, 'Title,' Journal, vol., no., pp., Year."
        raw_refs_with_gaps = """
        [1] K. Elissa, Title of paper without publication year, IEEE Transactions on Magnetics, vol 10.
        [2] M. Young, The Technical Writer's Handbook, Mill Valley, CA: University Science, 1989.
        """
        expected_llm_response = (
            "[1] K. Elissa, \"Title of paper without publication year,\" *IEEE Transactions on Magnetics*, vol. 10, [Điền ngày/tháng/năm].\n\n"
            "[2] M. Young, *The Technical Writer's Handbook*. Mill Valley, CA: University Science, 1989."
        )
        mock_genai, sys_mods = make_mock_genai_env()
        mock_genai.GenerativeModel.return_value.generate_content.return_value.text = expected_llm_response

        with patch.dict("sys.modules", sys_mods):
            formatted = format_references("key", ieee_rules, raw_refs_with_gaps)
            normalized = normalize_markdown_output(formatted)

        self.assertTrue(has_missing_placeholders(normalized))
        self.assertIn("[Điền ngày/tháng/năm]", normalized)
        self.assertIn("*IEEE Transactions on Magnetics*", normalized)

        html_out = generate_word_compatible_html(normalized)
        self.assertIn("background-color: #fff3cd", html_out)

    def test_scenario_3_uploaded_pdf_guideline_and_multi_source_citations(self):
        """
        Scenario 3: Uploaded PDF Guideline File + Multi-Source Raw References (Journal, Book, Web).
        Exercises: F4, F6, F7, F8, F13, F14.
        """
        mock_genai, sys_mods = make_mock_genai_env()
        fake_file = MagicMock()
        fake_file.state.name = "ACTIVE"
        fake_file.name = "files/scen-3-pdf"
        mock_genai.upload_file.return_value = fake_file

        mock_genai.GenerativeModel.return_value.generate_content.side_effect = [
            # 1st call: guideline extraction from PDF
            MagicMock(text="Tạp chí: [1] Tác giả. *Tạp chí*. Sách: [2] Tác giả. *Sách*. Web: [3] *Web*."),
            # 2nd call: reference formatting
            MagicMock(text=(
                "[1] Nguyen, V. (2021). *Nature AI*, 3, 45-56.\n\n"
                "[2] Goodfellow, I. (2016). *Deep Learning*. MIT Press.\n\n"
                "[3] WHO (2023). *Coronavirus report*. https://who.int/covid"
            )),
        ]

        with patch.dict("sys.modules", sys_mods):
            summary = extract_guideline_from_file_or_text(
                api_key="key",
                file_bytes=b"%PDF-1.5 multimodal content",
                filename="springer_sample.pdf",
            )
            formatted = format_references(
                api_key="key",
                guideline_summary=summary,
                raw_references="1. Nguyen 2021\n2. Goodfellow 2016\n3. WHO 2023",
            )
            normalized = normalize_markdown_output(formatted)

        self.assertIn("*Nature AI*", normalized)
        self.assertIn("*Deep Learning*", normalized)
        self.assertIn("*Coronavirus report*", normalized)
        mock_genai.delete_file.assert_called_with("files/scen-3-pdf")

    def test_scenario_4_uploaded_docx_guideline_and_book_web_citations(self):
        """
        Scenario 4: Uploaded Word (.docx) Guideline File + Book / Web Citations.
        Exercises: F5, F6, F7, F8, F13, F14.
        """
        mock_genai, sys_mods = make_mock_genai_env()
        mock_genai.GenerativeModel.return_value.generate_content.return_value.text = (
            "[1] Russell, S. & Norvig, P. (2020). *Artificial Intelligence: A Modern Approach* (4th ed.). Pearson.\n\n"
            "[2] OpenAI (2023). *GPT-4 Technical Report*. https://arxiv.org/abs/2303.08774"
        )
        mock_docx = MagicMock()
        mock_doc = MagicMock()
        mock_doc.paragraphs = [MagicMock(text="Quy chuẩn sách và website: Tên sách in nghiêng, URL cuối.")]
        mock_doc.tables = []
        mock_docx.Document.return_value = mock_doc
        sys_mods["docx"] = mock_docx

        with patch.dict("sys.modules", sys_mods):
            summary = extract_guideline_from_file_or_text(
                api_key="key",
                file_bytes=b"PK\x03\x04docx-bytes",
                filename="book_web_rules.docx",
            )
            formatted = format_references(
                api_key="key",
                guideline_summary=summary,
                raw_references="Russell Norvig AI 2020 Pearson\nOpenAI GPT-4 2023",
            )
            normalized = normalize_markdown_output(formatted)

        self.assertIn("*Artificial Intelligence: A Modern Approach*", normalized)
        self.assertIn("*GPT-4 Technical Report*", normalized)
        # Ensure genai.upload_file was NEVER called for docx
        mock_genai.upload_file.assert_not_called()

    def test_scenario_5_complex_multi_step_navigation_and_tweaked_guidelines_and_export(self):
        """
        Scenario 5: Complex Multi-Step Navigation & Tweaked Guidelines + HTML Export.
        Exercises: F8, F9, F10, F11, F12, F16.
        """
        # Step 1: User enters initial text
        step = 1
        guideline_text = "Initial journal guidelines: Chicago style"
        raw_refs = "1. Chicago ref raw"
        
        # Advance to Step 2
        step = 2
        guideline_summary = "Chicago 17th Style Notes: Author, 'Title', *Journal* Year."
        
        # User reviews and edits summary in Step 2
        guideline_summary += "\nSpecial requirement: Include DOI for all online journal entries."
        
        # User navigates back to Step 1 to verify
        step = 1
        self.assertEqual(guideline_text, "Initial journal guidelines: Chicago style")
        
        # User returns to Step 2
        step = 2
        self.assertIn("Special requirement", guideline_summary)
        
        # User advances to Step 3
        step = 3
        
        # In Step 3: user prepares raw references
        mock_genai, sys_mods = make_mock_genai_env()
        mock_genai.GenerativeModel.return_value.generate_content.return_value.text = (
            "[1] Gates, B. \"The Road Ahead,\" *Fortune*, 1995. https://doi.org/10.1000/1"
        )
        with patch.dict("sys.modules", sys_mods):
            result = format_references("key", guideline_summary, raw_refs)
            normalized = normalize_markdown_output(result)

        # Generate HTML export
        html_out = generate_word_compatible_html(normalized)
        self.assertIn("The Road Ahead", html_out)
        self.assertIn("<em>Fortune</em>", html_out)
        self.assertIn("https://doi.org/10.1000/1", html_out)
        self.assertIn("<!DOCTYPE html>", html_out)


if __name__ == "__main__":
    unittest.main()
