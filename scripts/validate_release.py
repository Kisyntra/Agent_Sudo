#!/usr/bin/env python3
"""Release validation safety checks for Agent_Sudo.

This script enforces:
1. Version matching across pyproject.toml, agent_sudo/__init__.py, and optionally a CLI/tag version.
2. No legacy package name install references in README.md.
3. Cryptographic integrity of the interoperability reference log.
"""

import argparse
import os
import re
import sys
import tomllib
from pathlib import Path

# Insert current working directory to prioritize local package resolution
sys.path.insert(0, str(Path.cwd()))
from agent_sudo.spec_helpers import verify_jsonl_file


def get_pyproject_version() -> str:
    pyproject_path = Path("pyproject.toml")
    if not pyproject_path.exists():
        print("Error: pyproject.toml not found.", file=sys.stderr)
        sys.exit(1)
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    return data["project"]["version"]


def get_init_version() -> tuple[str, str]:
    init_path = Path("agent_sudo/__init__.py")
    if not init_path.exists():
        print("Error: agent_sudo/__init__.py not found.", file=sys.stderr)
        sys.exit(1)
    content = init_path.read_text(encoding="utf-8")

    version = ""
    version_label = ""
    for line in content.splitlines():
        if line.startswith("__version__ ="):
            version = line.split("=")[1].strip().strip('"').strip("'")
        elif line.startswith("__version_label__ ="):
            version_label = line.split("=")[1].strip().strip('"').strip("'")

    return version, version_label


def validate_versions(expected_version: str | None = None) -> str:
    pyproject_ver = get_pyproject_version()
    init_ver, init_label = get_init_version()

    print(f"Checking version consistency:")
    print(f"  pyproject.toml version: {pyproject_ver}")
    print(f"  agent_sudo/__init__.py __version__: {init_ver}")
    print(f"  agent_sudo/__init__.py __version_label__: {init_label}")

    if pyproject_ver != init_ver:
        print("Error: Version in pyproject.toml and agent_sudo/__init__.py mismatch!", file=sys.stderr)
        sys.exit(1)

    expected_label = f"v{init_ver}"
    if init_label != expected_label:
        print(f"Error: __version_label__ ({init_label}) must match 'v{init_ver}'!", file=sys.stderr)
        sys.exit(1)

    # Check against CLI expected version if passed
    if expected_version:
        clean_expected = expected_version.lstrip("v")
        print(f"  Expected version input: {expected_version}")
        if init_ver != clean_expected:
            print(f"Error: Package version ({init_ver}) does not match expected version ({clean_expected})!", file=sys.stderr)
            sys.exit(1)

    # Verify tag matches if running in CI tag push trigger
    github_ref = os.environ.get("GITHUB_REF", "")
    github_ref_name = os.environ.get("GITHUB_REF_NAME", "")

    if github_ref.startswith("refs/tags/"):
        tag = github_ref_name
        expected_tag = f"v{init_ver}"
        print(f"  GitHub Action tag context: {tag}")
        if tag != expected_tag:
            print(f"Error: Git tag ({tag}) does not match expected release tag ({expected_tag})!", file=sys.stderr)
            sys.exit(1)

    return init_ver


def audit_readme() -> None:
    readme_path = Path("README.md")
    if not readme_path.exists():
        print("Error: README.md not found.", file=sys.stderr)
        sys.exit(1)

    content = readme_path.read_text(encoding="utf-8")
    print("Auditing README.md installation commands...")

    # Search for legacy install references in commands
    # e.g., 'pip install agent-sudo', 'pipx install agent-sudo'
    bad_install_patterns = [
        r"pip\s+install\s+agent-sudo(?!\-mcp)",
        r"pipx\s+install\s+agent-sudo(?!\-mcp)",
    ]

    for pattern in bad_install_patterns:
        matches = list(re.finditer(pattern, content))
        if matches:
            for match in matches:
                start = max(0, match.start() - 20)
                end = min(len(content), match.end() + 20)
                snippet = content[start:end].replace("\n", " ")
                print(f"Error: Found legacy install command reference in README.md: '{snippet}'", file=sys.stderr)
            sys.exit(1)

    print("README.md check passed.")


def verify_interop_assets() -> None:
    interop_path = Path("docs/interop/reference_log.jsonl")
    if not interop_path.exists():
        print(f"Error: Interop reference log not found at {interop_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Verifying cryptographic hash chain of {interop_path}...")
    res = verify_jsonl_file(interop_path)
    if not res.success:
        print(f"Error: Interoperability reference validation failed: {res}", file=sys.stderr)
        sys.exit(1)

    print("Interop reference log verification passed.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate release versions and assets.")
    parser.add_argument("--version", help="Expected version to validate against (e.g. 0.4.0)")
    args = parser.parse_args()

    version = validate_versions(expected_version=args.version)
    audit_readme()
    verify_interop_assets()
    print(f"\nSuccess: Release safety validation checks passed for version {version}.")


if __name__ == "__main__":
    main()
