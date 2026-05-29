# CI Reliability Guidelines & Autofix Boundaries

This document defines the continuous integration architecture, execution permissions, automated autofix scopes, and manual debugging guidelines for the `Agent_Sudo` repository.

---

## 1. CI Pipeline Architecture

Our validation pipeline consists of three core workflows:
1.  **Main Validation (`ci.yml`)**: Checks out the code, installs Python dependencies, runs the standard `unittest` discovery suite, checks for personal/sensitive data leakage, performs git diff whitespace validations, and compiles Python code to verify bytecode validity.
2.  **Security Analysis (`codeql.yml`)**: Runs standard static analysis (CodeQL) on pull requests and pushes to detect security vulnerabilities.
3.  **Mechanical Autofix (`autofix.yml`)**: Runs on pull requests to format code and fix trivial style issues automatically, pushing clean commits back to the source PR branch.

---

## 2. Automated Autofix Boundaries & Safety Rules

To maintain high security and cryptographic integrity in this project, **automated autofixing is restricted strictly to mechanical styling changes**.

### What Autofix CAN Fix
*   Mechanical formatting changes via `ruff format .`.
*   Safe, auto-fixable styling lints via `ruff check --fix .`.
*   Trailing whitespace and missing end-of-file newlines.

### What Autofix MUST NEVER Fix
To prevent silent logic rewrites, semantic changes, or tamper-evident log discrepancies, the following areas are strictly **out of scope** for automated fixes:
*   ❌ **Unsafe Fixes**: The `--unsafe-fixes` flag is completely prohibited.
*   ❌ **Unit Tests**: Test logic, asset configurations, or assertions.
*   ❌ **Verifier Behavior**: Hashing rules, padding, parsing, and log evaluation logic.
*   ❌ **Schema Definitions**: Schema models, field names, and taxonomies.
*   ❌ **Audit Hash-Chain Reference Files**: Under `docs/interop/` (like `reference_log.jsonl` or `reference_record.json`). These files must remain mathematically frozen unless manually regenerated.
*   ❌ **Security Policy Behavior**: Core gateway evaluation routines and fallback gating rules.
*   ❌ **Release Workflows**: Deployment and release automation scripts.

---

## 3. How to Debug CI Failures

1.  **Run Tests Locally**: Always run `PYTHONPATH=. pytest` or `PYTHONPATH=. python3 -m unittest discover -s tests` before pushing.
2.  **Whitespace Auditing**: Run `git diff --check` to locate trailing whitespace or carriage returns (`\r\n`) introduced by editors.
3.  **Inspect Ignored Files**: If a test succeeds locally but fails in CI with a missing file error, run `git check-ignore -v <path>` to check if the file was blocked by `.gitignore`.

---

## 4. Guidelines for Agentic Coding Assistants (like Antigravity)

When modifying code or running updates inside this repository:
1.  **Inspect CI Status**: Run `gh run list --repo Kisyntra/Agent_Sudo --limit 5` after pushes to confirm build status.
2.  **No Unsafe Flags**: Never implement lint fixes using `--unsafe-fixes`.
3.  **Strict Isolation**: Do not allow formatting tools to modify files in the `docs/interop/` reference folder. If changes occur, discard them via `git restore`.
4.  **Autofix Only on PRs**: The autofix workflow runs on PR branches. Never attempt to bypass branch protection rules to push formatting updates to `main`.
