#!/usr/bin/env python3
"""Repository integrity checks for PulseBridge Community Edition.

Uses only the Python standard library so it can run before project dependencies
are installed. It verifies the expected public repository surface and local
Markdown links. External URLs are intentionally not fetched.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_PATHS = (
    "README.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "START_HERE.md",
    "INSTALLATION.md",
    "PROTOCOL_SPEC.md",
    "BENCHMARK_METHODOLOGY.md",
    "HARDWARE_VALIDATION_CHECKLIST.md",
    "firmware/PulseBridgeESP32/PulseBridgeESP32.ino",
    "pi/app.py",
    "tests/test_protocol_v3.py",
    "tools/preflight.py",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/reproducibility_report.yml",
    ".github/workflows/protocol-smoke.yml",
)

MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")


def markdown_files() -> list[Path]:
    excluded = {".git", ".venv", "venv", "__pycache__"}
    return sorted(
        path
        for path in ROOT.rglob("*.md")
        if not any(part in excluded for part in path.parts)
    )


def local_link_target(source: Path, raw_target: str) -> Path | None:
    target = raw_target.strip()
    if not target or target.startswith(("#", "mailto:", "http://", "https://")):
        return None

    # Markdown destinations may optionally be wrapped in angle brackets.
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]

    # Ignore an optional Markdown link title after the destination.
    target = target.split(maxsplit=1)[0]
    target = unquote(target.split("#", 1)[0])
    if not target:
        return None

    if target.startswith("/"):
        return ROOT / target.lstrip("/")
    return source.parent / target


def main() -> int:
    errors: list[str] = []

    for relative in REQUIRED_PATHS:
        if not (ROOT / relative).exists():
            errors.append(f"missing required path: {relative}")

    for source in markdown_files():
        text = source.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK.finditer(text):
            raw_target = match.group(1)
            target = local_link_target(source, raw_target)
            if target is None:
                continue
            if not target.resolve().exists():
                display_source = source.relative_to(ROOT)
                errors.append(
                    f"broken local Markdown link in {display_source}: {raw_target}"
                )

    if errors:
        print("Repository integrity check failed:")
        for error in errors:
            print(f" - {error}")
        return 1

    print(
        "Repository integrity check passed: "
        f"{len(REQUIRED_PATHS)} required paths and "
        f"{len(markdown_files())} Markdown files checked."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
