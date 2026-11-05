#!/usr/bin/env python3
"""Validate Community Edition repository structure and local Markdown links."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_PATHS = (
    ".github/workflows/protocol-smoke.yml",
    "CONTRIBUTING.md",
    "HARDWARE_VALIDATION_CHECKLIST.md",
    "INSTALLATION.md",
    "LICENSE",
    "PROTOCOL_SPEC.md",
    "README.md",
    "START_HERE.md",
    "firmware/PulseBridgeESP32/PulseBridgeESP32.ino",
    "firmware/PulseBridgeESP32/board_config.h",
    "pi/app.py",
    "requirements.txt",
    "tests/test_community_smoke.py",
    "tests/test_protocol_v3.py",
)

MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")


def markdown_files(root: Path):
    excluded = {".git", ".venv", "venv", "node_modules"}
    for path in root.rglob("*.md"):
        if not excluded.intersection(path.relative_to(root).parts):
            yield path


def local_link_target(markdown_file: Path, raw_target: str) -> Path | None:
    target = raw_target.strip()
    if not target or target.startswith(("#", "http://", "https://", "mailto:")):
        return None
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    target = unquote(target.split("#", 1)[0].split("?", 1)[0])
    if not target:
        return None
    return (markdown_file.parent / target).resolve()


def check_repository(root: Path = ROOT) -> list[str]:
    errors: list[str] = []

    for relative in REQUIRED_PATHS:
        if not (root / relative).exists():
            errors.append(f"missing required path: {relative}")

    root_resolved = root.resolve()
    for markdown_file in markdown_files(root):
        text = markdown_file.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK.finditer(text):
            raw_target = match.group(1)
            target = local_link_target(markdown_file, raw_target)
            if target is None:
                continue
            try:
                target.relative_to(root_resolved)
            except ValueError:
                errors.append(
                    f"{markdown_file.relative_to(root)}: local link escapes repository: {raw_target}"
                )
                continue
            if not target.exists():
                errors.append(
                    f"{markdown_file.relative_to(root)}: broken local link: {raw_target}"
                )

    return errors


def main() -> int:
    errors = check_repository()
    if errors:
        print("Repository quality check FAILED:")
        for error in errors:
            print(f" - {error}")
        return 1

    print(
        "Repository quality check passed: required Community paths exist "
        "and local Markdown links resolve."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
