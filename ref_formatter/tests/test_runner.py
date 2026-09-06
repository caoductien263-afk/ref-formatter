"""
Automated Test Runner for Streamlit Gemini Reference Formatter.
Executes all test suites across Tiers 1-4, reports tier breakdown, and sets exit code.

Usage:
    python tests/test_runner.py
"""

import unittest
import sys
import time
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import test suites
import tests.test_gemini_service as t_gemini
import tests.test_formatter_utils as t_formatter
import tests.test_wizard_flow as t_wizard
import tests.test_e2e_scenarios as t_e2e
import tests.test_adversarial_stress as t_stress


def build_tier_suites():
    """Builds separate test suites organized by verification tiers."""
    loader = unittest.TestLoader()

    # Tier 1: Core Feature Coverage (F1 to F16)
    tier1_classes = [
        # F1 - F7 (Gemini service & dependencies)
        t_gemini.TestDependencySpecificationF1,
        t_gemini.TestApiKeyResolutionF2,
        t_gemini.TestEphemeralTempfileManagementF3,
        t_gemini.TestGeminiFileApiPdfProcessingF4,
        t_gemini.TestWordDocxIngestionF5,
        t_gemini.TestGuidelineExtractionPromptF6,
        t_gemini.TestReferenceFormattingPromptF7,
        # F8 - F12 (Wizard flow & session state)
        t_wizard.TestWizardStateMachineF8,
        t_wizard.TestVisualProgressStepperF9,
        t_wizard.TestStep2GuidelineInlineEditorF10,
        t_wizard.TestStep3ReferenceInputAndBackNavigationF11,
        t_wizard.TestGlobalStateResetF12,
        # F13 - F16 (Formatter utilities & Word export)
        t_formatter.TestMarkdownNormalizationF13,
        t_formatter.TestRichTextWordCopyPasteF14,
        t_formatter.TestMissingPlaceholderWarningF15,
        t_formatter.TestWordCompatibleHtmlExportF16,
    ]
    tier1_suite = unittest.TestSuite([loader.loadTestsFromTestCase(c) for c in tier1_classes])

    # Tier 2: Boundary & Corner Cases
    tier2_suite = loader.loadTestsFromTestCase(t_e2e.TestTier2BoundaryAndCornerCases)

    # Tier 3: Cross-Feature Combinations (Pairwise Coverage)
    tier3_suite = loader.loadTestsFromTestCase(t_e2e.TestTier3CrossFeatureCombinations)

    # Tier 4: Real-World Application Scenarios
    tier4_suite = loader.loadTestsFromTestCase(t_e2e.TestTier4RealWorldScenarios)

    # Tier 5: Adversarial & Stress Hardening
    tier5_classes = [
        t_stress.TestAdversarialReDoSAndPerformance,
        t_stress.TestAdversarialExtremeInputs,
        t_stress.TestAdversarialUnicodeAndEncodings,
        t_stress.TestAdversarialCitationNumberingAndDelimiters,
        t_stress.TestAdversarialUrlsAndDois,
        t_stress.TestAdversarialHtmlXssSanitization,
        t_stress.TestAdversarialPlaceholderVariations,
        t_stress.TestEphemeralTempfileFailureCleanup,
        t_stress.TestAdversarialBoundaryEdgeCases,
    ]
    tier5_suite = unittest.TestSuite([loader.loadTestsFromTestCase(c) for c in tier5_classes])

    return {
        "Tier 1: Feature Coverage (F1 - F16)": tier1_suite,
        "Tier 2: Boundary & Corner Cases": tier2_suite,
        "Tier 3: Cross-Feature Combinations (Pairwise)": tier3_suite,
        "Tier 4: Real-World Application Scenarios": tier4_suite,
        "Tier 5: Adversarial & Stress Hardening": tier5_suite,
    }


def run_all_tests():
    """Runs all test tiers with detailed reporting and returns overall success status."""
    print("=" * 80)
    print("  STREAMLIT GEMINI REFERENCE FORMATTER -- E2E TEST SUITE")
    print("=" * 80)
    start_total_time = time.time()

    tier_suites = build_tier_suites()
    all_success = True
    tier_results = {}
    total_ran = 0
    total_failed = 0
    total_errors = 0
    total_skipped = 0

    for tier_name, suite in tier_suites.items():
        print(f"\n--- Running {tier_name} ({suite.countTestCases()} tests) ---")
        runner = unittest.TextTestRunner(verbosity=1, stream=sys.stdout)
        result = runner.run(suite)

        passed = result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped)
        tier_results[tier_name] = {
            "ran": result.testsRun,
            "passed": passed,
            "failed": len(result.failures),
            "errors": len(result.errors),
            "skipped": len(result.skipped),
            "success": result.wasSuccessful(),
        }

        total_ran += result.testsRun
        total_failed += len(result.failures)
        total_errors += len(result.errors)
        total_skipped += len(result.skipped)

        if not result.wasSuccessful():
            all_success = False

    elapsed_time = time.time() - start_total_time

    # Print Summary Table
    print("\n" + "=" * 80)
    print("  TEST EXECUTION SUMMARY BY TIER")
    print("=" * 80)
    print(f"{'Tier Name':<48} | {'Total':<6} | {'Pass':<6} | {'Fail':<6} | {'Err':<6} | {'Status'}")
    print("-" * 80)
    for name, res in tier_results.items():
        status_label = "[PASS]" if res["success"] else "[FAIL]"
        print(
            f"{name:<48} | {res['ran']:<6} | {res['passed']:<6} | {res['failed']:<6} | {res['errors']:<6} | {status_label}"
        )
    print("-" * 80)
    total_status = "[ALL TIERS PASSED]" if all_success else "[TEST FAILURES DETECTED]"
    print(
        f"{'TOTAL':<48} | {total_ran:<6} | {total_ran - total_failed - total_errors - total_skipped:<6} | {total_failed:<6} | {total_errors:<6} | {total_status}"
    )
    print(f"\nTotal Time Elapsed: {elapsed_time:.2f}s")
    print("=" * 80)

    return all_success


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
