"""
Tier 1 Tests: Gemini Service & Dependencies (F1, F2, F3, F4, F5, F6, F7)
Tests dependency specifications, API key resolution hierarchy, ephemeral tempfile lifecycle,
PDF upload & polling, DOCX ingestion, and prompt structures.
"""

import unittest
from unittest.mock import patch, MagicMock
import os
import tempfile
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.gemini_service import (
    resolve_api_key,
    extract_docx_text,
    extract_guideline_from_file_or_text,
    format_references,
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


class TestDependencySpecificationF1(unittest.TestCase):
    """F1: Dependency Specification & Environment Sync."""

    def setUp(self):
        self.req_path = PROJECT_ROOT / "requirements.txt"

    def test_requirements_file_exists(self):
        """Test requirements.txt exists at root."""
        self.assertTrue(self.req_path.is_file(), "requirements.txt must exist at project root")

    def test_requirements_contains_streamlit(self):
        """Test requirements.txt specifies streamlit>=1.32.2."""
        content = self.req_path.read_text(encoding="utf-8")
        self.assertIn("streamlit", content)
        self.assertTrue(
            any("streamlit>=1.32" in line or "streamlit==1.32" in line for line in content.splitlines()),
            "requirements.txt must specify streamlit >= 1.32.2"
        )

    def test_requirements_contains_google_generativeai(self):
        """Test requirements.txt specifies google-generativeai>=0.7.2 (not broken 0.4.1)."""
        content = self.req_path.read_text(encoding="utf-8")
        self.assertIn("google-generativeai", content)
        self.assertNotIn(
            "google-generativeai==0.4.1",
            content,
            "google-generativeai==0.4.1 is broken (missing upload_file) and must not be used",
        )

    def test_requirements_contains_python_docx(self):
        """Test requirements.txt specifies python-docx>=1.1.0."""
        content = self.req_path.read_text(encoding="utf-8")
        self.assertIn("python-docx", content)

    def test_core_package_init_exports(self):
        """Test core package exports required functions."""
        import core
        expected_exports = [
            "resolve_api_key",
            "extract_guideline_from_file_or_text",
            "format_references",
            "normalize_markdown_output",
            "has_missing_placeholders",
            "generate_word_compatible_html",
        ]
        for exp in expected_exports:
            self.assertTrue(hasattr(core, exp), f"core package must export {exp}")


class TestApiKeyResolutionF2(unittest.TestCase):
    """F2: API Key Resolution Hierarchy."""

    def tearDown(self):
        if "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]

    def test_user_input_key_highest_priority(self):
        """Test user input key takes precedence over env var and secrets."""
        os.environ["GEMINI_API_KEY"] = "env-secret-key-123"
        resolved = resolve_api_key("user-direct-key-456")
        self.assertEqual(resolved, "user-direct-key-456")

    def test_env_var_fallback_when_user_input_empty(self):
        """Test fallback to os.environ when user input is None or whitespace."""
        os.environ["GEMINI_API_KEY"] = "env-key-789"
        self.assertEqual(resolve_api_key(None), "env-key-789")
        self.assertEqual(resolve_api_key("   "), "env-key-789")

    def test_st_secrets_fallback(self):
        """Test fallback to st.secrets when user key and env var are absent."""
        if "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]
            
        mock_st = MagicMock()
        mock_st.secrets = {"GEMINI_API_KEY": "streamlit-cloud-secret-key"}
        
        with patch.dict("sys.modules", {"streamlit": mock_st}):
            resolved = resolve_api_key(None)
            self.assertEqual(resolved, "streamlit-cloud-secret-key")

    def test_returns_none_when_unconfigured(self):
        """Test returns None cleanly when no key is set anywhere."""
        if "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]
            
        mock_st = MagicMock()
        mock_st.secrets = {}
        with patch.dict("sys.modules", {"streamlit": mock_st}):
            self.assertIsNone(resolve_api_key(None))

    def test_whitespace_trimmed_from_key(self):
        """Test whitespace is stripped from returned key."""
        self.assertEqual(resolve_api_key("  clean-key-999  "), "clean-key-999")

    def test_missing_secrets_toml_does_not_crash(self):
        """Test that missing .streamlit/secrets.toml (FileNotFoundError) is handled gracefully."""
        if "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]
            
        mock_st = MagicMock()
        type(mock_st).secrets = property(lambda self: (_ for _ in ()).throw(FileNotFoundError("No secrets.toml")))
        with patch.dict("sys.modules", {"streamlit": mock_st}):
            self.assertIsNone(resolve_api_key(None))


class TestEphemeralTempfileManagementF3(unittest.TestCase):
    """F3: Ephemeral Tempfile Management & Cleanup."""

    def test_tempfile_cleaned_up_on_successful_pdf_processing(self):
        """Test tempfile is deleted from disk after successful PDF processing."""
        created_paths = []
        original_named_temp = tempfile.NamedTemporaryFile

        def tracking_tempfile(*args, **kwargs):
            tf = original_named_temp(*args, **kwargs)
            created_paths.append(tf.name)
            return tf

        fake_model = MagicMock()
        fake_model.generate_content.return_value.text = "Rule summary"
        fake_file = MagicMock()
        fake_file.state.name = "ACTIVE"
        fake_file.name = "files/test-123"

        mock_genai, sys_mods = make_mock_genai_env()
        mock_genai.GenerativeModel.return_value = fake_model
        mock_genai.upload_file.return_value = fake_file

        with patch("tempfile.NamedTemporaryFile", side_effect=tracking_tempfile):
            with patch.dict("sys.modules", sys_mods):
                extract_guideline_from_file_or_text(
                    api_key="test-key",
                    file_bytes=b"%PDF-1.5 test content",
                    filename="sample.pdf",
                )

        self.assertTrue(len(created_paths) > 0, "NamedTemporaryFile should have been called")
        for path in created_paths:
            self.assertFalse(os.path.exists(path), f"Tempfile {path} was not cleaned up on success")

    def test_tempfile_cleaned_up_on_gemini_api_exception(self):
        """Test tempfile is deleted from disk in finally: block even if generate_content raises."""
        created_paths = []
        original_named_temp = tempfile.NamedTemporaryFile

        def tracking_tempfile(*args, **kwargs):
            tf = original_named_temp(*args, **kwargs)
            created_paths.append(tf.name)
            return tf

        fake_model = MagicMock()
        fake_model.generate_content.side_effect = RuntimeError("503 Service Unavailable")
        fake_file = MagicMock()
        fake_file.state.name = "ACTIVE"
        fake_file.name = "files/test-123"

        mock_genai, sys_mods = make_mock_genai_env()
        mock_genai.GenerativeModel.return_value = fake_model
        mock_genai.upload_file.return_value = fake_file

        with patch("tempfile.NamedTemporaryFile", side_effect=tracking_tempfile):
            with patch.dict("sys.modules", sys_mods):
                with self.assertRaises(RuntimeError):
                    extract_guideline_from_file_or_text(
                        api_key="test-key",
                        file_bytes=b"%PDF-1.5 content",
                        filename="sample.pdf",
                    )

        self.assertTrue(len(created_paths) > 0)
        for path in created_paths:
            self.assertFalse(os.path.exists(path), f"Tempfile {path} was not cleaned up on exception")

    def test_tempfile_cleaned_up_on_upload_exception(self):
        """Test tempfile is deleted if genai.upload_file raises an error."""
        created_paths = []
        original_named_temp = tempfile.NamedTemporaryFile

        def tracking_tempfile(*args, **kwargs):
            tf = original_named_temp(*args, **kwargs)
            created_paths.append(tf.name)
            return tf

        mock_genai, sys_mods = make_mock_genai_env()
        mock_genai.upload_file.side_effect = ConnectionError("Network unreachable")

        with patch("tempfile.NamedTemporaryFile", side_effect=tracking_tempfile):
            with patch.dict("sys.modules", sys_mods):
                with self.assertRaises(ConnectionError):
                    extract_guideline_from_file_or_text(
                        api_key="test-key",
                        file_bytes=b"%PDF-1.5 content",
                        filename="sample.pdf",
                    )

        self.assertTrue(len(created_paths) > 0)
        for path in created_paths:
            self.assertFalse(os.path.exists(path), f"Tempfile {path} was not cleaned up on upload error")

    def test_tempfile_suffix_is_pdf(self):
        """Test temporary file is created with .pdf suffix for correct MIME detection."""
        created_suffixes = []
        original_named_temp = tempfile.NamedTemporaryFile

        def tracking_tempfile(*args, **kwargs):
            created_suffixes.append(kwargs.get("suffix"))
            return original_named_temp(*args, **kwargs)

        fake_model = MagicMock()
        fake_model.generate_content.return_value.text = "Summary"
        fake_file = MagicMock()
        fake_file.state.name = "ACTIVE"
        fake_file.name = "files/test-123"

        mock_genai, sys_mods = make_mock_genai_env()
        mock_genai.GenerativeModel.return_value = fake_model
        mock_genai.upload_file.return_value = fake_file

        with patch("tempfile.NamedTemporaryFile", side_effect=tracking_tempfile):
            with patch.dict("sys.modules", sys_mods):
                extract_guideline_from_file_or_text(
                    api_key="test-key",
                    file_bytes=b"%PDF-1.5 content",
                    filename="document.final.pdf",
                )

        self.assertIn(".pdf", created_suffixes)

    def test_empty_bytes_handling_raises_without_tempfile_leak(self):
        """Test that empty file_bytes and empty text raises ValueError without file leaks."""
        with self.assertRaises(ValueError):
            extract_guideline_from_file_or_text(
                api_key="test-key",
                file_bytes=b"",
                filename="empty.pdf",
                text="",
            )


class TestGeminiFileApiPdfProcessingF4(unittest.TestCase):
    """F4: Gemini File API PDF Processing & Polling."""

    def test_pdf_upload_calls_genai_upload_file(self):
        """Test genai.upload_file is invoked with application/pdf."""
        mock_genai, sys_mods = make_mock_genai_env()
        fake_file = MagicMock()
        fake_file.state.name = "ACTIVE"
        mock_genai.upload_file.return_value = fake_file
        mock_genai.GenerativeModel.return_value.generate_content.return_value.text = "Analysis"

        with patch.dict("sys.modules", sys_mods):
            extract_guideline_from_file_or_text(
                api_key="test-key",
                file_bytes=b"%PDF-1.5 test",
                filename="guidelines.pdf",
            )

        mock_genai.upload_file.assert_called_once()
        call_kwargs = mock_genai.upload_file.call_args[1]
        self.assertEqual(call_kwargs.get("mime_type"), "application/pdf")

    def test_pdf_upload_polls_processing_to_active(self):
        """Test polling loop waits until file state transitions from PROCESSING to ACTIVE."""
        mock_genai, sys_mods = make_mock_genai_env()
        
        file_processing = MagicMock()
        file_processing.state.name = "PROCESSING"
        file_processing.name = "files/pdf-polled"
        
        file_active = MagicMock()
        file_active.state.name = "ACTIVE"
        file_active.name = "files/pdf-polled"

        mock_genai.upload_file.return_value = file_processing
        mock_genai.get_file.return_value = file_active
        mock_genai.GenerativeModel.return_value.generate_content.return_value.text = "Analysis"

        with patch("time.sleep", return_value=None):
            with patch.dict("sys.modules", sys_mods):
                extract_guideline_from_file_or_text(
                    api_key="test-key",
                    file_bytes=b"%PDF-1.5 test",
                    filename="guidelines.pdf",
                )

        mock_genai.get_file.assert_called_with("files/pdf-polled")

    def test_pdf_upload_remote_deletion_on_success(self):
        """Test genai.delete_file is called after successful content generation."""
        mock_genai, sys_mods = make_mock_genai_env()
        fake_file = MagicMock()
        fake_file.state.name = "ACTIVE"
        fake_file.name = "files/pdf-cleanup-test"
        mock_genai.upload_file.return_value = fake_file
        mock_genai.GenerativeModel.return_value.generate_content.return_value.text = "Analysis"

        with patch.dict("sys.modules", sys_mods):
            extract_guideline_from_file_or_text(
                api_key="test-key",
                file_bytes=b"%PDF-1.5 test",
                filename="guidelines.pdf",
            )

        mock_genai.delete_file.assert_called_once_with("files/pdf-cleanup-test")

    def test_pdf_upload_remote_deletion_on_error(self):
        """Test genai.delete_file is called in finally: block even when model raises."""
        mock_genai, sys_mods = make_mock_genai_env()
        fake_file = MagicMock()
        fake_file.state.name = "ACTIVE"
        fake_file.name = "files/pdf-err-cleanup"
        mock_genai.upload_file.return_value = fake_file
        mock_genai.GenerativeModel.return_value.generate_content.side_effect = RuntimeError("Quota error 429")

        with patch.dict("sys.modules", sys_mods):
            with self.assertRaises(RuntimeError):
                extract_guideline_from_file_or_text(
                    api_key="test-key",
                    file_bytes=b"%PDF-1.5 test",
                    filename="guidelines.pdf",
                )

        mock_genai.delete_file.assert_called_once_with("files/pdf-err-cleanup")

    def test_pdf_failed_state_raises_runtime_error(self):
        """Test that file entering FAILED state raises RuntimeError."""
        mock_genai, sys_mods = make_mock_genai_env()
        fake_file = MagicMock()
        fake_file.state.name = "FAILED"
        fake_file.name = "files/pdf-failed"
        mock_genai.upload_file.return_value = fake_file

        with patch.dict("sys.modules", sys_mods):
            with self.assertRaises(RuntimeError) as ctx:
                extract_guideline_from_file_or_text(
                    api_key="test-key",
                    file_bytes=b"%PDF-corrupt",
                    filename="guidelines.pdf",
                )
            self.assertIn("FAILED", str(ctx.exception))


class TestWordDocxIngestionF5(unittest.TestCase):
    """F5: Word (.docx) Ingestion via Local Parsing."""

    def test_extract_docx_paragraphs(self):
        """Test extract_docx_text extracts paragraphs from Document."""
        mock_docx = MagicMock()
        mock_doc = MagicMock()
        
        p1 = MagicMock()
        p1.text = "Quy chuẩn trích dẫn bài báo khoa học"
        p2 = MagicMock()
        p2.text = "Tác giả: Họ Tên, Năm, Tên bài báo"
        
        mock_doc.paragraphs = [p1, p2]
        mock_doc.tables = []
        mock_docx.Document.return_value = mock_doc

        with patch.dict("sys.modules", {"docx": mock_docx}):
            result = extract_docx_text(b"fake-docx-bytes")
            self.assertIn("Quy chuẩn trích dẫn", result)
            self.assertIn("Tác giả: Họ Tên", result)

    def test_extract_docx_tables(self):
        """Test extract_docx_text extracts and deduplicates table rows."""
        mock_docx = MagicMock()
        mock_doc = MagicMock()
        mock_doc.paragraphs = []
        
        mock_table = MagicMock()
        mock_row = MagicMock()
        c1 = MagicMock(text="Loại tài liệu")
        c2 = MagicMock(text="Định dạng yêu cầu")
        mock_row.cells = [c1, c2]
        mock_table.rows = [mock_row]
        mock_doc.tables = [mock_table]
        mock_docx.Document.return_value = mock_doc

        with patch.dict("sys.modules", {"docx": mock_docx}):
            result = extract_docx_text(b"fake-docx-bytes")
            self.assertIn("Bảng biểu trích xuất", result)
            self.assertIn("Loại tài liệu | Định dạng yêu cầu", result)

    def test_docx_avoids_genai_upload_file(self):
        """Test that .docx files do NOT call genai.upload_file (preventing 400 MIME error)."""
        mock_genai, sys_mods = make_mock_genai_env()
        mock_genai.GenerativeModel.return_value.generate_content.return_value.text = "Docx Summary"
        
        mock_docx = MagicMock()
        mock_doc = MagicMock()
        mock_p = MagicMock(text="Rule content")
        mock_doc.paragraphs = [mock_p]
        mock_doc.tables = []
        mock_docx.Document.return_value = mock_doc
        sys_mods["docx"] = mock_docx

        with patch.dict("sys.modules", sys_mods):
            extract_guideline_from_file_or_text(
                api_key="test-key",
                file_bytes=b"fake-docx-bytes",
                filename="guide.docx",
            )

        # genai.upload_file must NOT be called for .docx
        mock_genai.upload_file.assert_not_called()

    def test_docx_passed_as_text_in_contents(self):
        """Test that extracted docx text is appended as string in contents parameter."""
        mock_genai, sys_mods = make_mock_genai_env()
        mock_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model
        
        mock_docx = MagicMock()
        mock_doc = MagicMock()
        mock_p = MagicMock(text="Extracted Word guideline text")
        mock_doc.paragraphs = [mock_p]
        mock_doc.tables = []
        mock_docx.Document.return_value = mock_doc
        sys_mods["docx"] = mock_docx

        with patch.dict("sys.modules", sys_mods):
            extract_guideline_from_file_or_text(
                api_key="test-key",
                file_bytes=b"fake-docx-bytes",
                filename="guide.docx",
            )

        call_args = mock_model.generate_content.call_args[0][0]
        self.assertTrue(
            any("Extracted Word guideline text" in str(arg) for arg in call_args),
            "Extracted docx content must be in generate_content contents",
        )

    def test_unsupported_file_extension_raises_error(self):
        """Test unsupported extensions with non-text binary (e.g. .bin) raise ValueError."""
        mock_genai, sys_mods = make_mock_genai_env()
        with patch.dict("sys.modules", sys_mods):
            with self.assertRaises(ValueError):
                extract_guideline_from_file_or_text(
                    api_key="test-key",
                    file_bytes=b"\xff\xfe\x80\x81binarydata",
                    filename="unsupported.bin",
                )


class TestGuidelineExtractionPromptF6(unittest.TestCase):
    """F6: 8-Dimension Guideline Extraction Prompt Engineering."""

    def setUp(self):
        self.mock_genai, self.sys_mods = make_mock_genai_env()
        self.mock_model = MagicMock()
        self.mock_genai.GenerativeModel.return_value = self.mock_model
        self.mock_model.generate_content.return_value.text = "8-dimension guideline"

    def test_prompt_contains_all_8_dimensions(self):
        """Test the system prompt requests all 8 required citation dimensions."""
        with patch.dict("sys.modules", self.sys_mods):
            extract_guideline_from_file_or_text(
                api_key="test-key",
                text="Standard guideline text",
            )

        call_args = self.mock_model.generate_content.call_args[0][0]
        prompt = str(call_args[0])

        dimensions = [
            "Tạp chí khoa học",      # 1. Journal
            "Sách",                  # 2. Books
            "Kỷ yếu hội thảo",       # 3. Conference
            "Website",               # 4. Websites
            "tên tác giả",           # 5. Authors format
            "năm xuất bản",          # 6. Publication Year
            "tiêu đề",               # 7. Titles formatting
            "dấu câu",               # 8. Punctuation & volumes/pages/DOI
        ]
        for dim in dimensions:
            self.assertIn(dim.lower(), prompt.lower(), f"Prompt must contain dimension: {dim}")

    def test_user_text_appended_under_section_header(self):
        """Test that user guideline text is clearly delineated in prompt contents."""
        with patch.dict("sys.modules", self.sys_mods):
            extract_guideline_from_file_or_text(
                api_key="test-key",
                text="IEEE Citation Standard Rules",
            )

        call_args = self.mock_model.generate_content.call_args[0][0]
        contents_str = " ".join(str(c) for c in call_args)
        self.assertIn("IEEE Citation Standard Rules", contents_str)

    def test_both_text_and_pdf_included_in_contents(self):
        """Test that when both text and PDF are provided, both are included in contents."""
        fake_file = MagicMock()
        fake_file.state.name = "ACTIVE"
        self.mock_genai.upload_file.return_value = fake_file

        with patch.dict("sys.modules", self.sys_mods):
            extract_guideline_from_file_or_text(
                api_key="test-key",
                text="Additional notes on journal rules",
                file_bytes=b"%PDF-1.5 test",
                filename="rules.pdf",
            )

        call_args = self.mock_model.generate_content.call_args[0][0]
        self.assertIn(fake_file, call_args)
        self.assertTrue(any("Additional notes on journal rules" in str(c) for c in call_args))

    def test_missing_api_key_raises_value_error(self):
        """Test that empty API key raises ValueError before calling API."""
        with self.assertRaises(ValueError):
            extract_guideline_from_file_or_text(
                api_key="",
                text="Guideline text",
            )

    def test_missing_both_text_and_file_raises_value_error(self):
        """Test that providing neither text nor file raises ValueError."""
        with self.assertRaises(ValueError):
            extract_guideline_from_file_or_text(
                api_key="valid-key",
                text="",
                file_bytes=None,
            )


class TestReferenceFormattingPromptF7(unittest.TestCase):
    """F7: Reference Formatting Prompt Engineering & Placeholders."""

    def setUp(self):
        self.mock_genai, self.sys_mods = make_mock_genai_env()
        self.mock_model = MagicMock()
        self.mock_genai.GenerativeModel.return_value = self.mock_model
        self.mock_model.generate_content.return_value.text = "[1] Formatted reference."

    def test_prompt_enforces_double_newlines(self):
        """Test prompt mandates double newlines (\\n\\n) between references."""
        with patch.dict("sys.modules", self.sys_mods):
            format_references(
                api_key="test-key",
                guideline_summary="APA rules",
                raw_references="1. Nguyen Van A, AI paper",
            )

        prompt = str(self.mock_model.generate_content.call_args[0][0])
        self.assertIn("\\n\\n", prompt)
        self.assertIn("đoạn độc lập", prompt.lower())

    def test_prompt_enforces_markdown_italics(self):
        """Test prompt mandates *in nghiêng* for rich-text copy to Word."""
        with patch.dict("sys.modules", self.sys_mods):
            format_references(
                api_key="test-key",
                guideline_summary="APA rules",
                raw_references="1. Nguyen Van A, AI paper",
            )

        prompt = str(self.mock_model.generate_content.call_args[0][0])
        self.assertIn("*tên in nghiêng*", prompt)

    def test_prompt_enforces_anti_hallucination_placeholder(self):
        """Test prompt mandates literal [Điền ngày/tháng/năm] and forbids inventing missing data."""
        with patch.dict("sys.modules", self.sys_mods):
            format_references(
                api_key="test-key",
                guideline_summary="APA rules",
                raw_references="1. Nguyen Van A, AI paper",
            )

        prompt = str(self.mock_model.generate_content.call_args[0][0])
        self.assertIn("[Điền ngày/tháng/năm]", prompt)
        self.assertIn("TUYỆT ĐỐI KHÔNG tự bịa đặt", prompt)

    def test_prompt_enforces_order_preservation(self):
        """Test prompt commands keeping initial reference sequence from [1] to end."""
        with patch.dict("sys.modules", self.sys_mods):
            format_references(
                api_key="test-key",
                guideline_summary="APA rules",
                raw_references="1. Nguyen Van A, AI paper",
            )

        prompt = str(self.mock_model.generate_content.call_args[0][0])
        self.assertIn("GIỮ NGUYÊN HOÀN TOÀN THỨ TỰ", prompt)

    def test_prompt_forbids_code_blocks(self):
        """Test prompt instructs LLM not to wrap results in markdown code fences."""
        with patch.dict("sys.modules", self.sys_mods):
            format_references(
                api_key="test-key",
                guideline_summary="APA rules",
                raw_references="1. Nguyen Van A, AI paper",
            )

        prompt = str(self.mock_model.generate_content.call_args[0][0])
        self.assertIn("KHÔNG XUẤT CODE BLOCK", prompt)

    def test_missing_parameters_validation(self):
        """Test validation on empty api_key, empty summary, or empty raw_references."""
        with self.assertRaises(ValueError):
            format_references("", "summary", "raw refs")
        with self.assertRaises(ValueError):
            format_references("key", "", "raw refs")
        with self.assertRaises(ValueError):
            format_references("key", "summary", "")


if __name__ == "__main__":
    unittest.main()
