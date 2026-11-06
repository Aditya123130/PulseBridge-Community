"""Regression tests for fail-closed archived hardware-evidence validation."""

from __future__ import annotations

import copy
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.validate_hardware_evidence import (  # noqa: E402
    EvidenceError,
    assess_power_record,
    validate_directory,
    validate_summary,
)


class HardwareEvidenceValidationTests(unittest.TestCase):
    def setUp(self):
        self.summary = {
            "total": 4,
            "counts": {"BUY": 1, "SELL": 1, "STAY": 2, "WARMUP": 0},
            "errors": {"crc_errors": 0, "timeouts": 0},
            "error_count": 0,
            "sequence_gaps": 0,
            "resets": 0,
            "uptime_s": 5.0,
            "baud": 115200,
            "latency": {
                "min": 7000.0, "p50": 8200.0, "p95": 9100.0,
                "p99": 9500.0, "max": 10000.0, "avg": 8500.0,
                "window_n": 4,
            },
            "latest": [{"latency_us": 8500.0}],
        }

    def test_valid_accounting_is_not_misrepresented_as_recomputed(self):
        report = validate_summary(self.summary)
        self.assertTrue(report["summary_consistent"])
        self.assertFalse(report["raw_percentiles_recomputed"])
        self.assertEqual(report["messages"], 4)

    def test_decision_count_mismatch_fails(self):
        self.summary["counts"]["STAY"] += 1
        with self.assertRaisesRegex(EvidenceError, "decision counts"):
            validate_summary(self.summary)

    def test_error_count_mismatch_fails(self):
        self.summary["errors"]["crc_errors"] = 2
        with self.assertRaisesRegex(EvidenceError, "error categories"):
            validate_summary(self.summary)

    def test_invalid_latency_order_fails(self):
        self.summary["latency"]["p99"] = 8000.0
        with self.assertRaisesRegex(EvidenceError, "not monotonic"):
            validate_summary(self.summary)

    def test_nonfinite_and_negative_values_fail(self):
        for bad in (float("nan"), float("inf"), -1.0, True):
            case = copy.deepcopy(self.summary)
            case["latency"]["avg"] = bad
            with self.subTest(bad=bad), self.assertRaises(EvidenceError):
                validate_summary(case)

    def test_zero_or_missing_power_record_never_qualifies_performance(self):
        for health, expected in ((None, "unknown"), ("throttled=0x0", "flags_clear"),
                                 ("throttled=0x50005", "flagged")):
            with self.subTest(health=health):
                result = assess_power_record(health)
                self.assertFalse(result["performance_qualified"])
                self.assertEqual(result["power_status"], expected)

    def test_bad_power_record_is_unknown(self):
        self.assertEqual(assess_power_record("no throttle field")["power_status"], "unknown")
        self.assertEqual(assess_power_record("throttled=0x0\nthrottled=0x50005")["power_status"], "unknown")

    def test_validate_directory_checks_files(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = pathlib.Path(tempdir)
            (root / "summary.json").write_text(json.dumps(self.summary), encoding="utf-8")
            (root / "system_health.txt").write_text("throttled=0x50005\n", encoding="utf-8")
            report = validate_directory(root)
            self.assertEqual(report["power_status"], "flagged")
            self.assertFalse(report["performance_qualified"])
            self.assertEqual(report["messages"], 4)


if __name__ == "__main__":
    unittest.main()
