from __future__ import annotations

import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
SKIP_SUFFIXES = {".pyc", ".pyo"}

DEFAULT_MARKERS = [
    r"/Users/(?!username\b)[A-Za-z0-9._-]+",
    r"\bauth[_\-\s]?tokens?\b",
    r"\baccess_token\b",
    r"\brefresh_token\b",
    r"\bclient_secret\b",
    r"\bapi_key\b",
    r"\bbearer\s+[A-Za-z0-9._-]+",
]


def load_extra_markers() -> list[str]:
    raw = os.environ.get("AGENT_SUDO_PRIVATE_MARKERS", "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def compile_patterns() -> list[tuple[str, re.Pattern[str]]]:
    patterns: list[tuple[str, re.Pattern[str]]] = []
    for marker in DEFAULT_MARKERS:
        patterns.append(("sensitive marker", re.compile(marker, re.IGNORECASE)))

    for marker in load_extra_markers():
        patterns.append(("private marker", re.compile(re.escape(marker), re.IGNORECASE)))

    return patterns


def iter_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_dir() or path.suffix in SKIP_SUFFIXES:
            continue
        files.append(path)
    return files


def main() -> int:
    findings: list[str] = []
    patterns = compile_patterns()

    for path in iter_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        for line_number, line in enumerate(text.splitlines(), start=1):
            for label, pattern in patterns:
                if pattern.search(line):
                    rel = path.relative_to(ROOT)
                    findings.append(f"{rel}:{line_number}: {label}: {line.strip()}")

    if findings:
        print("Personal-data scan failed:")
        for finding in findings:
            print(finding)
        return 1

    print("Personal-data scan passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())