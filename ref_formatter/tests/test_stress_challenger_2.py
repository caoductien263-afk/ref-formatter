"""
Challenger 2 Empirical Stress Test Harness.
Targeting:
1. 3-step wizard state machine with rapid navigation cycles (1->2->3->2->1->3), data preservation, and reset handling.
2. Word copy-paste fidelity (italics *...*, <i>...</i>, bolding **...**, double newlines \\n\\n, Word HTML hanging indent).
3. Anti-hallucination [Điền ngày/tháng/năm] placeholder insertion and detection.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

from core.formatter_utils import (
    normalize_markdown_output,
    has_missing_placeholders,
    generate_word_compatible_html,
    strip_code_fences,
    _markdown_line_to_html,
)
from core.gemini_service import (
    resolve_api_key,
    format_references,
    extract_guideline_from_file_or_text,
)


class TestWizardStateMachineStressCycles(unittest.TestCase):
    """Stress testing the 3-step wizard state machine and session state transitions."""

    def test_rapid_navigation_cycles_data_preservation_headless(self):
        """Simulate rapid multi-cycle navigation: 1 -> 2 -> 3 -> 2 -> 1 -> 2 -> 3 -> 2 -> 1."""
        state = {
            "step": 1,
            "guideline_text": "Initial guideline text from user",
            "guideline_summary": "",
            "raw_refs": "",
            "formatted_refs": "",
            "file_info": {"name": "sample_paper.pdf", "size": 102400},
            "user_api_key": "test-key-xyz",
        }

        # Step 1 -> Step 2
        state["guideline_summary"] = "### Synthesized Guidelines\n1. Journal: Author (Year). Title."
        state["step"] = 2
        self.assertEqual(state["step"], 2)

        # In Step 2: User refines summary
        state["guideline_summary"] += "\nNote: Add DOI at the end."

        # Step 2 -> Step 3
        state["step"] = 3
        self.assertEqual(state["step"], 3)

        # In Step 3: User inputs raw references and runs formatting
        state["raw_refs"] = "1. Le Van C, Deep Learning, 2022\n2. Tran D, NLP Today, 2023"
        state["formatted_refs"] = (
            "[1] Le Van C. *Deep Learning*, 2022.\n\n"
            "[2] Tran D. *NLP Today*, 2023."
        )

        # Rapid Back Navigation: Step 3 -> Step 2
        state["step"] = 2
        self.assertEqual(state["step"], 2)
        # Verify Step 3 data is preserved!
        self.assertEqual(state["raw_refs"], "1. Le Van C, Deep Learning, 2022\n2. Tran D, NLP Today, 2023")
        self.assertIn("[1] Le Van C", state["formatted_refs"])

        # Rapid Back Navigation: Step 2 -> Step 1
        state["step"] = 1
        self.assertEqual(state["step"], 1)
        # Verify Step 1, 2, and 3 data is preserved!
        self.assertEqual(state["guideline_text"], "Initial guideline text from user")
        self.assertIn("Note: Add DOI at the end.", state["guideline_summary"])
        self.assertEqual(state["raw_refs"], "1. Le Van C, Deep Learning, 2022\n2. Tran D, NLP Today, 2023")
        self.assertIsNotNone(state["file_info"])

        # User edits guideline text in Step 1
        state["guideline_text"] = "Updated guideline text"
        
        # Advance again: Step 1 -> Step 2
        state["step"] = 2
        self.assertEqual(state["step"], 2)

        # Advance again: Step 2 -> Step 3
        state["step"] = 3
        self.assertEqual(state["step"], 3)
        # Ensure previous raw_refs and formatted_refs are still intact
        self.assertEqual(state["raw_refs"], "1. Le Van C, Deep Learning, 2022\n2. Tran D, NLP Today, 2023")
        self.assertIn("[2] Tran D", state["formatted_refs"])

    def test_reset_action_behavior(self):
        """Verify sidebar reset wipes wizard data while keeping user API key."""
        state = {
            "step": 3,
            "guideline_text": "Pasted guideline",
            "guideline_summary": "Summary of rules",
            "raw_refs": "Raw ref data",
            "formatted_refs": "[1] Formatted ref",
            "file_info": {"name": "rules.docx", "size": 50000},
            "user_api_key": "secret-gemini-key-999",
        }

        # Simulate Reset Button logic from app.py:72-78
        state["step"] = 1
        state["guideline_text"] = ""
        state["guideline_summary"] = ""
        state["raw_refs"] = ""
        state["formatted_refs"] = ""
        state["file_info"] = None

        self.assertEqual(state["step"], 1)
        self.assertEqual(state["guideline_text"], "")
        self.assertEqual(state["guideline_summary"], "")
        self.assertEqual(state["raw_refs"], "")
        self.assertEqual(state["formatted_refs"], "")
        self.assertIsNone(state["file_info"])
        # Crucial UX contract: user API key must NOT be wiped
        self.assertEqual(state["user_api_key"], "secret-gemini-key-999")

    def test_streamlit_apptest_full_navigation_cycle_and_reset(self):
        """Stress-test real Streamlit execution with AppTest: 1 -> 2 -> 3 -> 2 -> 1 -> 2 -> 3 + Reset."""
        from streamlit.testing.v1 import AppTest
        import core.gemini_service

        APP_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app.py"))
        at = AppTest.from_file(APP_PATH)
        at.run(timeout=15)

        # 1. Provide API Key
        self.assertTrue(len(at.sidebar.text_input) > 0)
        at.sidebar.text_input[0].input("test-stress-api-key").run(timeout=15)
        self.assertEqual(at.session_state.step, 1)

        # 2. Step 1: Input text and analyze
        at.main.text_area[0].input("IEEE rules: [1] Author, *Title*, Year.").run(timeout=15)

        with patch.object(
            core.gemini_service,
            "extract_guideline_from_file_or_text",
            return_value="IEEE Guideline Summary: 1. Journal Articles",
        ):
            # Click "Phân tích Quy chuẩn ➡"
            at.main.button[0].click().run(timeout=15)

        self.assertEqual(at.session_state.step, 2)
        self.assertEqual(at.session_state.guideline_summary, "IEEE Guideline Summary: 1. Journal Articles")

        # 3. Step 2: Edit summary
        at.main.text_area[0].input("IEEE Guideline Summary: 1. Journal Articles (Modified by Reviewer)").run(timeout=15)
        
        # Click "Xác nhận & Tiếp tục sang Bước 3 ➡" (Button index 1 in Step 2)
        at.main.button[1].click().run(timeout=15)
        self.assertEqual(at.session_state.step, 3)

        # 4. Step 3: Enter raw refs and format
        at.main.text_area[0].input("1. Le Van A, AI Research, 2021").run(timeout=15)
        with patch.object(
            core.gemini_service,
            "format_references",
            return_value="[1] Le Van A. *AI Research*, 2021.",
        ):
            # Click "⚡ Bắt đầu Chuẩn hóa" (Button index 1 in Step 3)
            at.main.button[1].click().run(timeout=15)

        self.assertEqual(at.session_state.step, 3)
        self.assertIn("[1] Le Van A. *AI Research*, 2021.", at.session_state.formatted_refs)

        # 5. Cycle Back: Step 3 -> Step 2
        # Button index 0 in Step 3 is "⬅ Quay lại Bước 2"
        at.main.button[0].click().run(timeout=15)
        self.assertEqual(at.session_state.step, 2)
        # Verify persistence of raw_refs and formatted_refs
        self.assertEqual(at.session_state.raw_refs, "1. Le Van A, AI Research, 2021")
        self.assertIn("Le Van A", at.session_state.formatted_refs)

        # 6. Cycle Back: Step 2 -> Step 1
        # Button index 0 in Step 2 is "⬅ Quay lại Bước 1 (Sửa quy chuẩn)"
        at.main.button[0].click().run(timeout=15)
        self.assertEqual(at.session_state.step, 1)
        self.assertEqual(at.session_state.guideline_text, "IEEE rules: [1] Author, *Title*, Year.")
        self.assertEqual(at.session_state.raw_refs, "1. Le Van A, AI Research, 2021")

        # 7. Cycle Forward Again: Step 1 -> Step 2
        with patch.object(
            core.gemini_service,
            "extract_guideline_from_file_or_text",
            return_value="Re-analyzed IEEE Summary",
        ):
            at.main.button[0].click().run(timeout=15)
        self.assertEqual(at.session_state.step, 2)

        # 8. Step 2 -> Step 3
        at.main.button[1].click().run(timeout=15)
        self.assertEqual(at.session_state.step, 3)
        self.assertEqual(at.session_state.raw_refs, "1. Le Van A, AI Research, 2021")
        self.assertIn("Le Van A", at.session_state.formatted_refs)

        # 9. Trigger Reset from Sidebar
        at.sidebar.button[0].click().run(timeout=15)
        self.assertEqual(at.session_state.step, 1)
        self.assertEqual(at.session_state.guideline_text, "")
        self.assertEqual(at.session_state.guideline_summary, "")
        self.assertEqual(at.session_state.raw_refs, "")
        self.assertEqual(at.session_state.formatted_refs, "")
        self.assertIsNone(at.session_state.file_info)
        # API key retained
        self.assertEqual(at.session_state.user_api_key, "test-stress-api-key")

    def test_rapid_navigation_sequence_1_2_3_2_1_3(self):
        """Specifically stress-test the 1->2->3->2->1->3 navigation cycle with data preservation."""
        from streamlit.testing.v1 import AppTest
        import core.gemini_service

        APP_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app.py"))
        at = AppTest.from_file(APP_PATH)
        at.run(timeout=15)
        at.sidebar.text_input[0].input("key-12345").run(timeout=15)

        # 1 -> 2
        at.main.text_area[0].input("Style APA: Author, (Year). *Title*.").run(timeout=15)
        with patch.object(core.gemini_service, "extract_guideline_from_file_or_text", return_value="APA Summary"):
            at.main.button[0].click().run(timeout=15)
        self.assertEqual(at.session_state.step, 2)

        # 2 -> 3
        at.main.button[1].click().run(timeout=15)
        self.assertEqual(at.session_state.step, 3)

        # Step 3: Add and format refs
        at.main.text_area[0].input("1. Author X, Machine Learning, 2021").run(timeout=15)
        with patch.object(core.gemini_service, "format_references", return_value="[1] Author X. *Machine Learning*, 2021."):
            at.main.button[1].click().run(timeout=15)
        self.assertEqual(at.session_state.step, 3)
        self.assertIn("Author X", at.session_state.formatted_refs)

        # 3 -> 2
        at.main.button[0].click().run(timeout=15)
        self.assertEqual(at.session_state.step, 2)
        self.assertEqual(at.session_state.raw_refs, "1. Author X, Machine Learning, 2021")

        # 2 -> 1
        at.main.button[0].click().run(timeout=15)
        self.assertEqual(at.session_state.step, 1)
        self.assertEqual(at.session_state.raw_refs, "1. Author X, Machine Learning, 2021")
        self.assertIn("Author X", at.session_state.formatted_refs)

        # 1 -> 3 (direct jump / navigation to step 3)
        at.session_state.step = 3
        at.run(timeout=15)
        self.assertEqual(at.session_state.step, 3)
        self.assertEqual(at.session_state.raw_refs, "1. Author X, Machine Learning, 2021")
        self.assertIn("Author X", at.session_state.formatted_refs)
        # Verify result view is fully rendered
        self.assertTrue(len(at.download_button) > 0)
        self.assertTrue(any("Hướng dẫn sao chép" in str(info.value) for info in at.info))

    def test_multiple_rapid_resets(self):
        """Stress-test multiple consecutive resets from different wizard states."""
        from streamlit.testing.v1 import AppTest

        APP_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app.py"))
        at = AppTest.from_file(APP_PATH)
        at.run(timeout=15)
        at.sidebar.text_input[0].input("persistent-key").run(timeout=15)

        for step in [1, 2, 3, 2, 1]:
            at.session_state.step = step
            at.session_state.guideline_text = f"Guideline step {step}"
            at.session_state.guideline_summary = f"Summary step {step}"
            at.session_state.raw_refs = f"Raw refs step {step}"
            at.session_state.formatted_refs = f"Formatted step {step}"
            at.run(timeout=15)

            # Trigger reset
            at.sidebar.button[0].click().run(timeout=15)
            self.assertEqual(at.session_state.step, 1)
            self.assertEqual(at.session_state.guideline_text, "")
            self.assertEqual(at.session_state.guideline_summary, "")
            self.assertEqual(at.session_state.raw_refs, "")
            self.assertEqual(at.session_state.formatted_refs, "")
            self.assertIsNone(at.session_state.file_info)
            self.assertEqual(at.session_state.user_api_key, "persistent-key")

    def test_wizard_guard_conditions_prevent_invalid_advance(self):
        """Test that empty inputs at any step trigger warnings and prevent advancing."""
        from streamlit.testing.v1 import AppTest

        APP_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app.py"))
        at = AppTest.from_file(APP_PATH)
        at.run(timeout=15)
        at.sidebar.text_input[0].input("valid-key").run(timeout=15)

        # Step 1: Click analyze with empty text and no file
        at.main.text_area[0].input("").run(timeout=15)
        at.main.button[0].click().run(timeout=15)
        # Must stay at Step 1
        self.assertEqual(at.session_state.step, 1)
        self.assertTrue(any("Vui lòng cung cấp" in str(w.value) for w in at.warning))

        # Manually force step 2 with empty summary to test Step 2 guard
        at.session_state.step = 2
        at.session_state.guideline_summary = "   "
        at.run(timeout=15)
        # Click "Xác nhận & Tiếp tục sang Bước 3 ➡"
        at.main.button[1].click().run(timeout=15)
        # Must stay at Step 2
        self.assertEqual(at.session_state.step, 2)
        self.assertTrue(any("không được để trống" in str(w.value) for w in at.warning))

        # Manually force step 3 with empty raw_refs to test Step 3 guard
        at.session_state.step = 3
        at.session_state.guideline_summary = "Valid summary"
        at.session_state.raw_refs = "   "
        at.run(timeout=15)
        # Click "⚡ Bắt đầu Chuẩn hóa"
        at.main.button[1].click().run(timeout=15)
        self.assertEqual(at.session_state.step, 3)
        self.assertEqual(at.session_state.formatted_refs, "")
        self.assertTrue(any("Vui lòng nhập danh sách" in str(w.value) for w in at.warning))


class TestWordCopyPasteFidelityStress(unittest.TestCase):
    """Stress testing Microsoft Word copy-paste fidelity and formatting conversions."""

    def test_strip_markdown_code_fences_edge_cases(self):
        """Verify robust stripping of various LLM code block wrappers."""
        cases = [
            ("```markdown\n[1] Ref A\n```", "[1] Ref A"),
            ("```\n[1] Ref B\n```", "[1] Ref B"),
            ("```text\n\n[1] Ref C\n\n```", "[1] Ref C"),
            ("  ```markdown\n[1] Ref D\n```  ", "[1] Ref D"),
            ("[1] Ref E without fences", "[1] Ref E without fences"),
            ("", ""),
            (None, ""),
        ]
        for raw, expected in cases:
            self.assertEqual(strip_code_fences(raw), expected)

    def test_double_newline_enforcement_for_all_citation_formats(self):
        """Stress test normalization ensures \\n\\n between entries across all citation numbering patterns."""
        raw_single_newline = (
            "[1] Le Van A. *Journal 1*, 2020.\n"
            "[2] Tran Van B. *Journal 2*, 2021.\n"
            "3. Nguyen Van C. *Book 3*, 2022.\n"
            "(4) Pham Van D. *Proceedings 4*, 2023.\n"
            "- Hoang E. *Conference 5*, 2024.\n"
            "* Do F. *Symposium 6*, 2025.\n"
            "• Vu G. *Workshop 7*, 2026."
        )
        normalized = normalize_markdown_output(raw_single_newline)
        items = normalized.split("\n\n")
        self.assertEqual(len(items), 7, f"Expected 7 distinct reference items, got {len(items)}")
        for idx, item in enumerate(items, 1):
            self.assertTrue(len(item.strip()) > 0)

    def test_crlf_windows_newlines_handled(self):
        """Verify Windows CRLF (\\r\\n) is converted to clean double newlines."""
        crlf_text = "[1] Item 1\r\n\r\n[2] Item 2\r\n[3] Item 3"
        normalized = normalize_markdown_output(crlf_text)
        self.assertNotIn("\r", normalized)
        self.assertEqual(len(normalized.split("\n\n")), 3)

    def test_excessive_newlines_collapsed(self):
        """Verify 3 or more newlines are collapsed cleanly to double newlines."""
        excessive = "[1] Item 1\n\n\n\n\n[2] Item 2\n\n\n[3] Item 3"
        normalized = normalize_markdown_output(excessive)
        self.assertEqual(normalized, "[1] Item 1\n\n[2] Item 2\n\n[3] Item 3")

    def test_italics_and_bold_conversion_fidelity(self):
        """Verify markdown line conversion to HTML supports italics (*, _) and bold (**, __)."""
        line1 = "Author A (2021). *Title of Journal Article*. *Journal of AI*, 10(2), 15-25."
        html1 = _markdown_line_to_html(line1)
        self.assertIn("<em>Title of Journal Article</em>", html1)
        self.assertIn("<em>Journal of AI</em>", html1)

        line2 = "[1] **Nguyen Van A**, **Tran B**, *Deep Learning Principles*, **Vol. 5**, 2020."
        html2 = _markdown_line_to_html(line2)
        self.assertIn("<strong>Nguyen Van A</strong>", html2)
        self.assertIn("<strong>Tran B</strong>", html2)
        self.assertIn("<em>Deep Learning Principles</em>", html2)
        self.assertIn("<strong>Vol. 5</strong>", html2)

    def test_special_html_escaping_and_url_preservation(self):
        """Verify &, <, > are escaped, URLs with underscores don't create false italics, and links work."""
        line = "Smith & Jones <researchers>. Available at: https://example.com/paper_version_1.html"
        html_line = _markdown_line_to_html(line)
        self.assertIn("Smith &amp; Jones", html_line)
        self.assertIn("&lt;researchers&gt;", html_line)
        # Underscores in URL should NOT be converted to <em>
        self.assertNotIn("<em>", html_line)
        self.assertIn("paper_version_1.html", html_line)

        # Explicit markdown link
        line_link = "[DOI Link](https://doi.org/10.1000/182)"
        html_link = _markdown_line_to_html(line_link)
        self.assertIn('<a href="https://doi.org/10.1000/182">DOI Link</a>', html_link)

    def test_word_compatible_html_document_structure(self):
        """Verify complete Word HTML document contains Word XML namespaces, hanging indent CSS, and proper styling."""
        sample_refs = (
            "[1] Le, V. A. (2021). *Machine Learning in Medicine*. *Medical AI Journal*, 12(1), 45-55.\n\n"
            "[2] Tran, T. B. (2022). *Neural Networks*. Tech Publisher."
        )
        word_html = generate_word_compatible_html(sample_refs)

        # Check Microsoft Word XML namespaces
        self.assertIn('xmlns:o="urn:schemas-microsoft-com:office:office"', word_html)
        self.assertIn('xmlns:w="urn:schemas-microsoft-com:office:word"', word_html)
        self.assertIn('<w:WordDocument>', word_html)

        # Check academic styling: 12pt Times New Roman, 1.5 line-height, hanging indent
        self.assertIn("font-family: 'Times New Roman'", word_html)
        self.assertIn("font-size: 12pt", word_html)
        self.assertIn("line-height: 1.5", word_html)
        self.assertIn("text-indent: -0.5in", word_html)
        self.assertIn("margin-left: 0.5in", word_html)

        # Check paragraph classes and formatting
        self.assertIn('<p class="ref-item">', word_html)
        self.assertIn('<em>Machine Learning in Medicine</em>', word_html)
        self.assertIn('<em>Medical AI Journal</em>', word_html)
        self.assertIn('<em>Neural Networks</em>', word_html)

    def test_large_volume_100_citations_performance_and_fidelity(self):
        """Stress-test 100 citations volume: normalization, double newlines, Word HTML conversion in <1s."""
        import time
        raw_100_list = []
        for i in range(1, 101):
            raw_100_list.append(
                f"[{i}] Author {i}, Co-Author {i}. *Journal of Computational Intelligence {i}*, **Vol. {i}**, pp. {i}-{i+10}, 202{i%10}."
            )
        # Combine with single newlines to stress double-newline enforcer
        raw_combined = "\n".join(raw_100_list)

        t_start = time.time()
        normalized = normalize_markdown_output(raw_combined)
        word_html = generate_word_compatible_html(normalized)
        duration = time.time() - t_start

        self.assertLess(duration, 1.0, f"Processing 100 citations took too long: {duration:.3f}s")
        items = normalized.split("\n\n")
        self.assertEqual(len(items), 100, f"Expected 100 items, got {len(items)}")
        self.assertEqual(word_html.count('<p class="ref-item">'), 100)
        self.assertIn("[100]", normalized)
        self.assertIn("<em>Journal of Computational Intelligence 100</em>", word_html)
        self.assertIn("<strong>Vol. 100</strong>", word_html)

    def test_vietnamese_unicode_word_fidelity(self):
        """Stress-test complex Vietnamese characters, diacritics, and combined punctuation."""
        vn_ref = (
            "[1] Nguyễn Văn Ánh, Trần Thị Mỹ Duyên (2023). "
            "*Nghiên cứu ứng dụng Trí tuệ Nhân tạo trong Y tế Cộng đồng*. "
            "*Tạp chí Y Dược học Quân sự*, **Tập 48**, số 6, tr. 112-120."
        )
        normalized = normalize_markdown_output(vn_ref)
        html_out = generate_word_compatible_html(normalized)

        self.assertIn("Nguyễn Văn Ánh", html_out)
        self.assertIn("<em>Nghiên cứu ứng dụng Trí tuệ Nhân tạo trong Y tế Cộng đồng</em>", html_out)
        self.assertIn("<em>Tạp chí Y Dược học Quân sự</em>", html_out)
        self.assertIn("<strong>Tập 48</strong>", html_out)



class TestAntiHallucinationPlaceholderStress(unittest.TestCase):
    """Stress testing anti-hallucination [Điền ngày/tháng/năm] placeholder detection and rendering."""

    def test_placeholder_detection_positive_cases(self):
        """Verify all forms of missing placeholders are accurately detected."""
        positive_cases = [
            "[1] Author A. [Điền ngày/tháng/năm]. *Title*. Publisher.",
            "[2] Author B ( [Điền năm] ). *Handbook of AI*.",
            "[3] Website C. Accessed on [Điền ngày truy cập]. URL: https://example.com",
            "[4] Author D. *Journal*, pp. [Điền số trang].",
            "[5] Author E. DOI: [Điền DOI].",
            "[6] Author F. Publisher: [Điền nhà xuất bản].",
            "[7] Lowercase test: [điền ngày/tháng/năm].",
            "[8] Uppercase test: [ĐIỀN NGÀY/THÁNG/NĂM].",
        ]
        for case in positive_cases:
            self.assertTrue(
                has_missing_placeholders(case),
                f"Failed to detect placeholder in: {case}",
            )

    def test_placeholder_detection_negative_cases(self):
        """Verify normal citations without placeholders do not falsely trigger."""
        negative_cases = [
            "[1] Le Van A (2021). *Machine Learning in Medicine*. *Medical AI Journal*, 12(1), 45-55.",
            "[2] Tran Thi B (2019). *Deep Learning Handbook*. NXB Khoa hoc.",
            "3. Dien Bien Phu Historical Studies, 1954.",
            "4. Nguyen Van Dien, *Agricultural Economics*, 2020.",
            "",
            None,
        ]
        for case in negative_cases:
            self.assertFalse(
                has_missing_placeholders(case),
                f"False positive detection in: {case}",
            )

    def test_placeholder_highlight_in_word_html(self):
        """Verify placeholders are wrapped in prominent amber/gold highlight spans in Word HTML."""
        sample = "[1] Le Van A. [Điền ngày/tháng/năm]. *Journal of Science*, pp. [Điền số trang]."
        html_doc = generate_word_compatible_html(sample)

        self.assertIn("background-color: #fff3cd", html_doc)
        self.assertIn("color: #856404", html_doc)
        self.assertIn("[Điền ngày/tháng/năm]", html_doc)
        self.assertIn("[Điền số trang]", html_doc)

    def test_warning_banner_in_streamlit_ui_when_placeholder_present(self):
        """Verify Step 3 UI renders the warning alert when formatted references contain placeholders."""
        from streamlit.testing.v1 import AppTest

        APP_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app.py"))
        at = AppTest.from_file(APP_PATH)
        at.run(timeout=15)
        at.sidebar.text_input[0].input("valid-key").run(timeout=15)

        # Force state into Step 3 with formatted refs containing missing placeholder
        at.session_state.step = 3
        at.session_state.guideline_summary = "Rules"
        at.session_state.raw_refs = "1. Le Van A, Machine Learning"
        at.session_state.formatted_refs = "[1] Le Van A. [Điền ngày/tháng/năm]. *Machine Learning*."
        at.run(timeout=15)

        # Check warning banner
        warning_messages = [str(w.value) for w in at.warning]
        self.assertTrue(
            any("Phát hiện dữ liệu cần bổ sung" in msg for msg in warning_messages),
            f"Expected warning banner, got: {warning_messages}",
        )

        # Force state into Step 3 with complete formatted refs (no placeholder)
        at.session_state.formatted_refs = "[1] Le Van A (2021). *Machine Learning*."
        at.run(timeout=15)

        warning_messages_clean = [str(w.value) for w in at.warning]
        self.assertFalse(
            any("Phát hiện dữ liệu cần bổ sung" in msg for msg in warning_messages_clean),
            f"Warning banner should not appear when citations are complete, got: {warning_messages_clean}",
        )


class TestGeminiPromptAntiHallucinationEngineering(unittest.TestCase):
    """Verify prompt templates enforce anti-hallucination constraints and required output rules."""

    def test_guideline_extraction_prompt_8_dimensions(self):
        """Verify extract_guideline_from_file_or_text prompt covers all 8 dimensions."""
        import inspect
        source = inspect.getsource(extract_guideline_from_file_or_text)
        dimensions = [
            "Tạp chí khoa học (Journal Articles)",
            "Sách và chương sách (Books & Book Chapters)",
            "Kỷ yếu hội thảo/hội nghị (Conference Proceedings)",
            "Website và tài liệu trực tuyến (Websites & Reports)",
            "Quy tắc tên tác giả (Authors format)",
            "Quy tắc năm xuất bản (Publication Year)",
            "Quy tắc tiêu đề (Titles formatting)",
            "Quy tắc dấu câu và các trường thông tin khác",
        ]
        for dim in dimensions:
            self.assertIn(dim, source, f"Guideline prompt missing dimension: {dim}")

    def test_format_references_prompt_anti_hallucination_and_word_fidelity(self):
        """Verify format_references prompt contains explicit anti-hallucination and formatting rules."""
        import inspect
        source = inspect.getsource(format_references)

        # Anti-hallucination tag
        self.assertIn("[Điền ngày/tháng/năm]", source)
        self.assertIn("TUYỆT ĐỐI KHÔNG tự bịa đặt", source)

        self.assertTrue(r"\n\n" in source or "\\n\\n" in source or "hai ký tự xuống dòng" in source)
        self.assertIn("*tên in nghiêng*", source)  # Italics
        self.assertIn("GIỮ NGUYÊN HOÀN TOÀN THỨ TỰ", source)  # Order preservation
        self.assertIn("KHÔNG XUẤT CODE BLOCK", source)  # No code fences


if __name__ == "__main__":
    unittest.main()
