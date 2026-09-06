"""
Streamlit Gemini Reference Formatter
Automated academic reference formatting based on journal guidelines using Google Gemini API.
"""

import os
import streamlit as st
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

# --- Streamlit Page Configuration ---
st.set_page_config(
    page_title="AI Reference Formatter",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Session State Initialization ---
if "step" not in st.session_state:
    st.session_state.step = 1
if "guideline_text" not in st.session_state:
    st.session_state.guideline_text = ""
if "guideline_summary" not in st.session_state:
    st.session_state.guideline_summary = ""
if "raw_refs" not in st.session_state:
    st.session_state.raw_refs = ""
if "formatted_refs" not in st.session_state:
    st.session_state.formatted_refs = ""
if "file_info" not in st.session_state:
    st.session_state.file_info = None
if "user_api_key" not in st.session_state:
    st.session_state.user_api_key = ""

# --- Sidebar: Configuration & API Key ---
with st.sidebar:
    st.header("⚙️ Cấu hình hệ thống")
    user_key_input = st.text_input(
        "Nhập Google Gemini API Key:",
        type="password",
        value=st.session_state.user_api_key,
        help="Lấy khóa API từ Google AI Studio để sử dụng dịch vụ.",
    )
    if user_key_input != st.session_state.user_api_key:
        st.session_state.user_api_key = user_key_input

    st.markdown(
        "[👉 Lấy API Key miễn phí tại Google AI Studio](https://aistudio.google.com/app/apikey)"
    )

    # Resolve active API key
    active_api_key = resolve_api_key(st.session_state.user_api_key)

    # API Key status badge
    if active_api_key:
        st.success("✅ Đã kết nối API Key")
    else:
        st.warning("⚠️ Chưa cấu hình API Key")

    st.divider()

    # Reset button
    if st.button("🔄 Làm mới toàn bộ (Bắt đầu lại)", use_container_width=True):
        st.session_state.step = 1
        st.session_state.guideline_text = ""
        st.session_state.guideline_summary = ""
        st.session_state.raw_refs = ""
        st.session_state.formatted_refs = ""
        st.session_state.file_info = None
        st.rerun()

    st.caption("Phiên bản: 1.0.0 | Hỗ trợ Word (.docx) & PDF")


# --- Main Header & Stepper UI ---
st.title("📚 AI Format Tài Liệu Tham Khảo")
st.markdown(
    "Ứng dụng tự động chuẩn hóa định dạng Tài liệu Tham khảo khoa học theo yêu cầu của từng tạp chí "
    "sử dụng **Google Gemini Multimodal AI**."
)

# Visual Progress Stepper
step_cols = st.columns(3)
step_names = [
    "1. Quy chuẩn tạp chí",
    "2. Phê duyệt quy chuẩn",
    "3. Định dạng & Xuất Word",
]
current_step = st.session_state.step

for idx, col in enumerate(step_cols, start=1):
    with col:
        if idx < current_step:
            st.success(f"✓ {step_names[idx - 1]}")
        elif idx == current_step:
            st.info(f"👉 **{step_names[idx - 1]}**")
        else:
            st.text(f"⚪ {step_names[idx - 1]}")

st.divider()

# Guard: Check API Key
if not active_api_key:
    st.info(
        "👈 **Vui lòng nhập Google Gemini API Key ở menu bên trái** "
        "(hoặc thiết lập biến môi trường `GEMINI_API_KEY` / `st.secrets`) để bắt đầu."
    )
    st.stop()


# ==============================================================================
# BƯỚC 1: CUNG CẤP QUY CHUẨN TẠP CHÍ
# ==============================================================================
if st.session_state.step == 1:
    st.header("Bước 1: Cung cấp quy chuẩn tạp chí")
    st.markdown(
        "Bạn có thể dán đoạn văn bản quy định của tạp chí, hoặc tải lên bài báo mẫu (PDF/Word). "
        "AI sẽ phân tích cấu trúc trích dẫn theo 8 tiêu chí chuẩn mực."
    )

    # Text area bound to session state
    input_text = st.text_area(
        "Dán văn bản quy chuẩn tạp chí (Nếu có):",
        value=st.session_state.guideline_text,
        height=160,
        placeholder="Ví dụ: Tạp chí yêu cầu trích dẫn theo thứ tự xuất hiện [1], tên tác giả viết Họ Tên, tên tạp chí in nghiêng...",
    )
    st.session_state.guideline_text = input_text

    # File uploader
    uploaded_file = st.file_uploader(
        "Hoặc tải lên tệp bài báo mẫu / quy định (PDF hoặc DOCX):",
        type=["pdf", "docx"],
        help="Hỗ trợ file PDF (phân tích trực tiếp qua Gemini File API) và Word DOCX (trích xuất nội dung văn bản).",
    )

    if uploaded_file is not None:
        st.session_state.file_info = {
            "name": uploaded_file.name,
            "size": uploaded_file.size,
        }
        st.caption(f"📁 Tệp đã chọn: **{uploaded_file.name}** ({uploaded_file.size / 1024:.1f} KB)")
    elif st.session_state.file_info is not None:
        st.caption(f"📁 Tệp đã phân tích trước đó: **{st.session_state.file_info.get('name')}**")

    if st.button("Phân tích Quy chuẩn ➡", type="primary"):
        file_bytes = uploaded_file.getvalue() if uploaded_file else None
        filename = uploaded_file.name if uploaded_file else None

        if not st.session_state.guideline_text.strip() and not file_bytes:
            st.warning("⚠️ Vui lòng cung cấp văn bản quy chuẩn hoặc tải lên ít nhất một tệp PDF/DOCX.")
        else:
            with st.spinner("AI đang đọc và tổng hợp quy chuẩn trích dẫn theo 8 chiều kích thước..."):
                try:
                    summary = extract_guideline_from_file_or_text(
                        api_key=active_api_key,
                        text=st.session_state.guideline_text,
                        file_bytes=file_bytes,
                        filename=filename,
                    )
                    st.session_state.guideline_summary = summary
                    st.session_state.step = 2
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Đã xảy ra lỗi trong quá trình phân tích: {e}")


# ==============================================================================
# BƯỚC 2: PHÊ DUYỆT VÀ TINH CHỈNH QUY CHUẨN
# ==============================================================================
elif st.session_state.step == 2:
    st.header("Bước 2: Phê duyệt và tinh chỉnh quy chuẩn")
    st.success("🎉 AI đã tổng hợp quy chuẩn thành công! Bạn có thể xem và tinh chỉnh trực tiếp bên dưới:")

    # Editable area for user refinement
    edited_summary = st.text_area(
        "Nội dung quy chuẩn (Có thể chỉnh sửa hoặc bổ sung thêm lưu ý):",
        value=st.session_state.guideline_summary,
        height=320,
    )
    st.session_state.guideline_summary = edited_summary

    with st.expander("👁️ Xem trước hiển thị định dạng (Markdown)", expanded=False):
        st.markdown(st.session_state.guideline_summary)

    col_back, col_next = st.columns([1, 4])
    with col_back:
        if st.button("⬅ Quay lại Bước 1 (Sửa quy chuẩn)"):
            st.session_state.step = 1
            st.rerun()
    with col_next:
        if st.button("Xác nhận & Tiếp tục sang Bước 3 ➡", type="primary"):
            if not st.session_state.guideline_summary.strip():
                st.warning("⚠️ Nội dung quy chuẩn không được để trống.")
            else:
                st.session_state.step = 3
                st.rerun()


# ==============================================================================
# BƯỚC 3: ĐỊNH DẠNG TÀI LIỆU THAM KHẢO & XUẤT WORD
# ==============================================================================
elif st.session_state.step == 3:
    st.header("Bước 3: Định dạng Tài liệu tham khảo & Xuất Word")

    with st.expander("📖 Xem lại quy chuẩn đã phê duyệt", expanded=False):
        st.markdown(st.session_state.guideline_summary)

    # Raw references text area
    input_raw = st.text_area(
        "Dán danh sách TLTK thô của bạn vào đây (Mỗi tài liệu 1 dòng hoặc cách nhau rõ ràng):",
        value=st.session_state.raw_refs,
        height=240,
        placeholder="Ví dụ:\n1. Nguyen Van A, Machine Learning in Healthcare, Journal of AI, 2021, vol 10, pp 20-30\n2. Tran Thi B, Deep Learning Handbook, NXB Khoa hoc, 2019",
    )
    st.session_state.raw_refs = input_raw

    col_back_step2, col_format = st.columns([1, 4])
    with col_back_step2:
        if st.button("⬅ Quay lại Bước 2"):
            st.session_state.step = 2
            st.rerun()
    with col_format:
        if st.button("⚡ Bắt đầu Chuẩn hóa", type="primary"):
            if not st.session_state.raw_refs.strip():
                st.warning("⚠️ Vui lòng nhập danh sách TLTK thô cần chuẩn hóa.")
            else:
                with st.spinner("AI đang xử lý và chuẩn hóa danh sách theo đúng quy chuẩn..."):
                    try:
                        raw_result = format_references(
                            api_key=active_api_key,
                            guideline_summary=st.session_state.guideline_summary,
                            raw_references=st.session_state.raw_refs,
                        )
                        normalized_result = normalize_markdown_output(raw_result)
                        st.session_state.formatted_refs = normalized_result
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Đã xảy ra lỗi khi chuẩn hóa: {e}")

    # Display results if available
    if st.session_state.formatted_refs:
        st.divider()
        st.subheader("🎉 Kết quả đã chuẩn hóa")

        # Copy-to-Word instruction badge
        st.info(
            "📋 **Hướng dẫn sao chép vào Microsoft Word**:\n"
            "Bôi đen phần kết quả bên dưới, nhấn **Ctrl+C** (hoặc Cmd+C) và dán (**Ctrl+V**) thẳng vào Microsoft Word. "
            "Định dạng in nghiêng, in đậm và ngắt đoạn độc lập sẽ được giữ nguyên 100%!"
        )

        # Warning for missing placeholders
        if has_missing_placeholders(st.session_state.formatted_refs):
            st.warning(
                "⚠️ **Phát hiện dữ liệu cần bổ sung**: Một số tài liệu thiếu thông tin (năm, số trang, ngày truy cập...) "
                "đã được đánh dấu dạng **[Điền ngày/tháng/năm]** hoặc **[Điền ...]**. "
                "Vui lòng kiểm tra và bổ sung trước khi nộp bài."
            )

        # HTML Download button for Word opening
        html_content = generate_word_compatible_html(st.session_state.formatted_refs)
        st.download_button(
            label="📥 Tải tệp HTML (Mở trực tiếp bằng Microsoft Word)",
            data=html_content.encode("utf-8"),
            file_name="tai_lieu_tham_khao_chuan_hoa.html",
            mime="text/html",
        )

        # Render formatted references using st.markdown
        st.markdown(st.session_state.formatted_refs, unsafe_allow_html=True)
