#!/usr/bin/env python3
"""Validate archived PulseBridge hardware evidence without claiming benchmark qualification.

This checks *internal consistency* of recorded summary values. It cannot
reconstruct latency percentiles without raw measurements or certify a physical
experiment. Only Python's standard library is required.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

DEFAULT_EVIDENCE_DIR = (
    Path(__file__).resolve().parents[1] / "docs" / "hardware-validation" / "2026-11-05"
)


class EvidenceError(ValueError):
    """A captured evidence record is malformed or internally inconsistent."""


def _nonnegative_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EvidenceError(f"{field} must be a non-negative integer")
    return value


def _nonnegative_finite(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceError(f"{field} must be a finite non-negative number")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise EvidenceError(f"{field} must be a finite non-negative number")
    return result


def validate_summary(summary: dict[str, Any]) -> dict[str, Any]:
    """Validate an archived run's accounting, errors and reported quantiles.

    Quantiles are range-checked, **not** recalculated: this JSON is a snapshot,
    not a complete list of all request-to-decision samples.
    """
    if not isinstance(summary, dict):
        raise EvidenceError("summary must be a JSON object")
    total = _nonnegative_integer(summary.get("total"), "total")
    counts = summary.get("counts")
    if not isinstance(counts, dict) or not counts:
        raise EvidenceError("counts must be a non-empty object")
    count_sum = sum(_nonnegative_integer(value, f"counts.{key}") for key, value in counts.items())
    if count_sum != total:
        raise EvidenceError(f"decision counts sum to {count_sum}, expected total {total}")

    errors = summary.get("errors")
    if not isinstance(errors, dict) or not errors:
        raise EvidenceError("errors must be a non-empty object")
    error_sum = sum(_nonnegative_integer(value, f"errors.{key}") for key, value in errors.items())
    error_count = _nonnegative_integer(summary.get("error_count"), "error_count")
    if error_sum != error_count:
        raise EvidenceError(f"error categories sum to {error_sum}, expected error_count {error_count}")
    gaps = _nonnegative_integer(summary.get("sequence_gaps"), "sequence_gaps")
    resets = _nonnegative_integer(summary.get("resets"), "resets")

    uptime = _nonnegative_finite(summary.get("uptime_s"), "uptime_s")
    if uptime == 0 and total > 0:
        raise EvidenceError("nonzero total with zero uptime")
    baud = _nonnegative_integer(summary.get("baud"), "baud")
    if baud == 0:
        raise EvidenceError("baud must be greater than zero")
    latency = summary.get("latency")
    if not isinstance(latency, dict):
        raise EvidenceError("latency must be an object")
    quantiles = {
        name: _nonnegative_finite(latency.get(name), f"latency.{name}")
        for name in ("min", "p50", "p95", "p99", "max", "avg")
    }
    if not (quantiles["min"] <= quantiles["p50"] <= quantiles["p95"]
            <= quantiles["p99"] <= quantiles["max"]):
        raise EvidenceError("reported latency quantiles are not monotonic")
    if not quantiles["min"] <= quantiles["avg"] <= quantiles["max"]:
        raise EvidenceError("average latency falls outside the recorded range")
    window_n = _nonnegative_integer(latency.get("window_n"), "latency.window_n")
    if window_n > total:
        raise EvidenceError("latency.window_n exceeds total messages")

    latest = summary.get("latest", [])
    if not isinstance(latest, list):
        raise EvidenceError("latest must be a list")
    if len(latest) > total:
        raise EvidenceError("latest snapshot contains more rows than total messages")
    for i, sample in enumerate(latest):
        if not isinstance(sample, dict):
            raise EvidenceError(f"latest[{i}] must be an object")
        _nonnegative_finite(sample.get("latency_us"), f"latest[{i}].latency_us")

    return {
        "messages": total,
        "error_categories_total": error_sum,
        "sequence_gaps": gaps,
        "resets": resets,
        "latency_window_n": window_n,
        "latest_snapshot_n": len(latest),
        "summary_consistent": True,
        "raw_percentiles_recomputed": False,
    }


def assess_power_record(system_health: str | None) -> dict[str, Any]:
    """Do not promote a snapshot to 'qualified benchmark' on power flags alone."""
    if not system_health:
        return {
            "throttled_mask": None,
            "power_status": "unknown",
            "performance_qualified": False,
            "reason": "Power evidence absent; full benchmark qualification not established",
        }
    matches = re.findall(r"(?m)^\s*throttled=(0x[0-9a-fA-F]+)\s*$", system_health)
    if len(matches) != 1:
        return {
            "throttled_mask": None,
            "power_status": "unknown",
            "performance_qualified": False,
            "reason": "Exactly one usable throttled=0x... record is required",
        }
    mask = int(matches[0], 16)
    return {
        "throttled_mask": matches[0],
        "power_status": "flagged" if mask else "flags_clear",
        "performance_qualified": False,
        "reason": (
            "Undervoltage/throttling flags were recorded; latency is preliminary"
            if mask else
            "Power flags are clear, but repeatability, clock and methodology still need qualification"
        ),
    }


def validate_directory(evidence_dir: Path) -> dict[str, Any]:
    summary_path = evidence_dir / "summary.json"
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot read a valid {summary_path}: {exc}") from exc
    result = validate_summary(summary)
    health_path = evidence_dir / "system_health.txt"
    try:
        health = health_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        health = None
    result.update(assess_power_record(health))
    result["evidence_dir"] = str(evidence_dir)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE_DIR)
    args = parser.parse_args(argv)
    try:
        result = validate_directory(args.evidence_dir)
    except EvidenceError as exc:
        print(f"Evidence validation FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
