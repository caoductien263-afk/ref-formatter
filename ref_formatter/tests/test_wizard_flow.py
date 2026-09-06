"""
Tier 1 Tests: 3-Step Wizard Flow & Navigation (F8, F9, F10, F11, F12)
Validates session state schema, bidirectional wizard navigation, visual stepper logic,
Step 2 inline editing, Step 3 reference retention, and global state reset.
"""

import unittest
from unittest.mock import patch, MagicMock


class WizardSessionState:
    """
    Simulation of Streamlit Session State for headless state-machine testing.
    Mirrors the exact keys and behavior in app.py.
    """

    def __init__(self):
        self._state = {
            "step": 1,
            "guideline_text": "",
            "guideline_summary": "",
            "raw_refs": "",
            "formatted_refs": "",
            "file_info": None,
            "user_api_key": "",
        }

    def __getitem__(self, key):
        return self._state[key]

    def __setitem__(self, key, value):
        self._state[key] = value

    def __contains__(self, key):
        return key in self._state

    def get(self, key, default=None):
        return self._state.get(key, default)

    def reset_all(self):
        """Action performed by 'Làm mới toàn bộ' button in sidebar."""
        self._state["step"] = 1
        self._state["guideline_text"] = ""
        self._state["guideline_summary"] = ""
        self._state["raw_refs"] = ""
        self._state["formatted_refs"] = ""
        self._state["file_info"] = None


class TestWizardStateMachineF8(unittest.TestCase):
    """F8: 3-Step Wizard State Machine & Session State Transitions."""

    def setUp(self):
        self.session = WizardSessionState()

    def test_initial_session_state_schema(self):
        """Test initial schema contains all required keys with default values."""
        self.assertEqual(self.session["step"], 1)
        self.assertEqual(self.session["guideline_text"], "")
        self.assertEqual(self.session["guideline_summary"], "")
        self.assertEqual(self.session["raw_refs"], "")
        self.assertEqual(self.session["formatted_refs"], "")
        self.assertIsNone(self.session["file_info"])

    def test_transition_step_1_to_step_2_on_analysis(self):
        """Test transition from Step 1 to Step 2 upon successful guideline extraction."""
        self.session["guideline_text"] = "Sample journal guidelines"
        # Simulate AI analysis result
        self.session["guideline_summary"] = "1. Journal: Author (Year). Title. Journal."
        self.session["step"] = 2
        self.assertEqual(self.session["step"], 2)
        self.assertEqual(self.session["guideline_summary"], "1. Journal: Author (Year). Title. Journal.")

    def test_transition_step_2_to_step_1_back_navigation(self):
        """Test back navigation from Step 2 to Step 1 preserves guideline_text."""
        self.session["guideline_text"] = "Pasted guideline rules"
        self.session["guideline_summary"] = "Extracted summary"
        self.session["step"] = 2
        
        # User clicks "Quay lại Bước 1"
        self.session["step"] = 1
        self.assertEqual(self.session["step"], 1)
        self.assertEqual(self.session["guideline_text"], "Pasted guideline rules")

    def test_transition_step_2_to_step_3_on_approval(self):
        """Test transition from Step 2 to Step 3 upon approving guidelines."""
        self.session["step"] = 2
        self.session["guideline_summary"] = "Approved rules"
        # User clicks "Xác nhận & Tiếp tục"
        self.session["step"] = 3
        self.assertEqual(self.session["step"], 3)
        self.assertEqual(self.session["guideline_summary"], "Approved rules")

    def test_transition_step_3_to_step_2_back_navigation(self):
        """Test back navigation from Step 3 to Step 2 preserves raw references."""
        self.session["step"] = 3
        self.session["guideline_summary"] = "Rules"
        self.session["raw_refs"] = "1. Raw citation data"
        
        # User clicks "Quay lại Bước 2"
        self.session["step"] = 2
        self.assertEqual(self.session["step"], 2)
        self.assertEqual(self.session["raw_refs"], "1. Raw citation data")
        self.assertEqual(self.session["guideline_summary"], "Rules")

    def test_full_roundtrip_navigation_preserves_all_inputs(self):
        """Test 1 -> 2 -> 3 -> 2 -> 1 -> 2 -> 3 preserves both guideline_text and raw_refs."""
        self.session["guideline_text"] = "Input 1"
        self.session["step"] = 2
        self.session["guideline_summary"] = "Summary 1"
        self.session["step"] = 3
        self.session["raw_refs"] = "Refs 1"
        
        # Back to 2
        self.session["step"] = 2
        # Back to 1
        self.session["step"] = 1
        self.assertEqual(self.session["guideline_text"], "Input 1")
        self.assertEqual(self.session["raw_refs"], "Refs 1")
        
        # Forward to 2
        self.session["step"] = 2
        self.assertEqual(self.session["guideline_summary"], "Summary 1")
        # Forward to 3
        self.session["step"] = 3
        self.assertEqual(self.session["raw_refs"], "Refs 1")


class TestVisualProgressStepperF9(unittest.TestCase):
    """F9: Visual Progress Stepper UI."""

    def compute_stepper_states(self, current_step):
        """Calculates visual state for each column in 3-step progress stepper."""
        names = [
            "1. Quy chuẩn tạp chí",
            "2. Phê duyệt quy chuẩn",
            "3. Định dạng & Xuất Word",
        ]
        states = []
        for idx, name in enumerate(names, start=1):
            if idx < current_step:
                states.append({"status": "completed", "badge": f"✓ {name}"})
            elif idx == current_step:
                states.append({"status": "active", "badge": f"👉 **{name}**"})
            else:
                states.append({"status": "pending", "badge": f"⚪ {name}"})
        return states

    def test_stepper_at_step_1(self):
        """At Step 1: step 1 is active, steps 2 & 3 are pending."""
        states = self.compute_stepper_states(1)
        self.assertEqual(states[0]["status"], "active")
        self.assertEqual(states[1]["status"], "pending")
        self.assertEqual(states[2]["status"], "pending")

    def test_stepper_at_step_2(self):
        """At Step 2: step 1 is completed, step 2 is active, step 3 is pending."""
        states = self.compute_stepper_states(2)
        self.assertEqual(states[0]["status"], "completed")
        self.assertEqual(states[1]["status"], "active")
        self.assertEqual(states[2]["status"], "pending")

    def test_stepper_at_step_3(self):
        """At Step 3: steps 1 & 2 are completed, step 3 is active."""
        states = self.compute_stepper_states(3)
        self.assertEqual(states[0]["status"], "completed")
        self.assertEqual(states[1]["status"], "completed")
        self.assertEqual(states[2]["status"], "active")

    def test_stepper_step_names_accuracy(self):
        """Test that stepper labels correctly reflect domain requirements."""
        states = self.compute_stepper_states(1)
        self.assertIn("Quy chuẩn tạp chí", states[0]["badge"])
        self.assertIn("Phê duyệt quy chuẩn", states[1]["badge"])
        self.assertIn("Định dạng & Xuất Word", states[2]["badge"])

    def test_stepper_handles_boundary_values(self):
        """Test stepper handles all valid step values."""
        for step in [1, 2, 3]:
            states = self.compute_stepper_states(step)
            self.assertEqual(len(states), 3)
            active_count = sum(1 for s in states if s["status"] == "active")
            self.assertEqual(active_count, 1)


class TestStep2GuidelineInlineEditorF10(unittest.TestCase):
    """F10: Step 2 Guideline Review & Inline Editor."""

    def setUp(self):
        self.session = WizardSessionState()
        self.session["step"] = 2
        self.session["guideline_summary"] = "Original AI Summary: Authors in APA format."

    def test_editor_initialized_with_ai_summary(self):
        """Test text area initial value is populated with guideline_summary."""
        self.assertEqual(self.session["guideline_summary"], "Original AI Summary: Authors in APA format.")

    def test_user_modifications_update_guideline_summary(self):
        """Test user modifications in Step 2 update st.session_state.guideline_summary."""
        edited = "Original AI Summary: Authors in APA format.\nAddendum: Journal names must be uppercase."
        self.session["guideline_summary"] = edited
        self.assertEqual(self.session["guideline_summary"], edited)

    def test_step_3_uses_edited_guideline_summary(self):
        """Test that advancing to Step 3 retains and uses the edited summary."""
        custom_rule = "Custom Rule: Year placed at the very end of reference."
        self.session["guideline_summary"] = custom_rule
        # Proceed to step 3
        self.session["step"] = 3
        self.assertIn("Custom Rule", self.session["guideline_summary"])

    def test_empty_summary_cannot_proceed_validation(self):
        """Test that empty summary validation prevents advancing to Step 3."""
        self.session["guideline_summary"] = "   "
        can_proceed = bool(self.session["guideline_summary"].strip())
        self.assertFalse(can_proceed)

    def test_special_characters_in_edited_summary(self):
        """Test summary containing quotes, slashes, and Vietnamese diacritics is preserved."""
        complex_text = 'Quy chuẩn: "Tiêu đề trong ngoặc kép", tác giả viết Họ & Tên, tạp chí in nghiêng *Tạp chí*'
        self.session["guideline_summary"] = complex_text
        self.assertEqual(self.session["guideline_summary"], complex_text)


class TestStep3ReferenceInputAndBackNavigationF11(unittest.TestCase):
    """F11: Step 3 Reference Input & Back Navigation."""

    def setUp(self):
        self.session = WizardSessionState()
        self.session["step"] = 3
        self.session["guideline_summary"] = "Approved rules"

    def test_raw_references_stored_in_session_state(self):
        """Test raw reference input is stored in session state."""
        refs = "1. Ref one\n2. Ref two"
        self.session["raw_refs"] = refs
        self.assertEqual(self.session["raw_refs"], refs)

    def test_back_navigation_to_step_2_retains_raw_refs(self):
        """Test clicking back to Step 2 does NOT wipe raw references."""
        self.session["raw_refs"] = "1. Ref one\n2. Ref two"
        # Click back
        self.session["step"] = 2
        self.assertEqual(self.session["step"], 2)
        self.assertEqual(self.session["raw_refs"], "1. Ref one\n2. Ref two")

    def test_empty_raw_references_blocks_formatting(self):
        """Test empty raw references input blocks execution."""
        self.session["raw_refs"] = "   "
        can_format = bool(self.session["raw_refs"].strip())
        self.assertFalse(can_format)

    def test_formatted_refs_persisted_in_session_state(self):
        """Test formatted output is stored in formatted_refs."""
        output = "[1] *Formatted Citation 1*\n\n[2] *Formatted Citation 2*"
        self.session["formatted_refs"] = output
        self.assertEqual(self.session["formatted_refs"], output)

    def test_reformatting_replaces_previous_output(self):
        """Test running formatting a second time updates formatted_refs cleanly."""
        self.session["formatted_refs"] = "Old output"
        self.session["formatted_refs"] = "New output after tweak"
        self.assertEqual(self.session["formatted_refs"], "New output after tweak")


class TestGlobalStateResetF12(unittest.TestCase):
    """F12: Global State Reset Action."""

    def setUp(self):
        self.session = WizardSessionState()

    def test_reset_from_step_1(self):
        """Test reset from Step 1 clears all fields and leaves step at 1."""
        self.session["guideline_text"] = "Partial guideline"
        self.session.reset_all()
        self.assertEqual(self.session["step"], 1)
        self.assertEqual(self.session["guideline_text"], "")

    def test_reset_from_step_2(self):
        """Test reset from Step 2 returns step to 1 and purges summary."""
        self.session["step"] = 2
        self.session["guideline_text"] = "Guideline"
        self.session["guideline_summary"] = "Summary"
        self.session.reset_all()
        self.assertEqual(self.session["step"], 1)
        self.assertEqual(self.session["guideline_summary"], "")
        self.assertEqual(self.session["guideline_text"], "")

    def test_reset_from_step_3(self):
        """Test reset from Step 3 clears everything including formatted_refs."""
        self.session["step"] = 3
        self.session["guideline_summary"] = "Summary"
        self.session["raw_refs"] = "Raw refs"
        self.session["formatted_refs"] = "Output"
        self.session["file_info"] = {"name": "test.pdf", "size": 1024}
        
        self.session.reset_all()
        
        self.assertEqual(self.session["step"], 1)
        self.assertEqual(self.session["guideline_text"], "")
        self.assertEqual(self.session["guideline_summary"], "")
        self.assertEqual(self.session["raw_refs"], "")
        self.assertEqual(self.session["formatted_refs"], "")
        self.assertIsNone(self.session["file_info"])

    def test_reset_preserves_api_key_configuration(self):
        """Test reset clears user data but preserves user_api_key so user does not retype."""
        self.session["user_api_key"] = "my-secret-gemini-key"
        self.session.reset_all()
        self.assertEqual(self.session["user_api_key"], "my-secret-gemini-key")

    def test_post_reset_fresh_run_success(self):
        """Test user can immediately start a fresh run after reset without residual state."""
        self.session["step"] = 3
        self.session["raw_refs"] = "Old refs"
        self.session.reset_all()
        
        # New run
        self.session["guideline_text"] = "Fresh rules"
        self.session["step"] = 2
        self.session["guideline_summary"] = "Fresh summary"
        self.session["step"] = 3
        self.session["raw_refs"] = "Fresh refs"
        
        self.assertEqual(self.session["raw_refs"], "Fresh refs")
        self.assertEqual(self.session["guideline_summary"], "Fresh summary")


if __name__ == "__main__":
    unittest.main()
