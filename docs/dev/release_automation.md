# Release Automation Guide (Phase 1 — Dry-Run Only)

> [!IMPORTANT]
> This guide describes **Phase 1 Dry-Run Release Automation**. 
> * PyPI Trusted Publishing/OIDC setup is designated as **future work**.
> * The final publishing steps (both PyPI upload and GitHub Release creation) remain strictly **manual** and are commented out in our workflows until explicitly approved for deployment.

---

## 1. Safety Validation Pipeline

To ensure that only stable, fully compatible, and verified packages are built, our release workflow executes a sequence of automated safety gates:

1. **Ruff Linter & Formatter**: Ensures python formatting and styling checks pass.
2. **Unit Tests**: Runs the full `unittest` suite.
3. **Release Validation Script** (`scripts/validate_release.py`):
   * **Version Consistency**: Ensures version numbers in `pyproject.toml`, `agent_sudo/__init__.py`, and the target tag/input version match exactly.
   * **Readme Safety Audit**: Checks that the `README.md` only references `agent-sudo-mcp` for PyPI/installation commands (blocking legacy `pip install agent-sudo` commands).
   * **Cryptographic Integrity**: Runs the verifier (`verify_jsonl_file()`) against the interoperability reference log `docs/interop/reference_log.jsonl` to guarantee spec compliance.
4. **Build & Twine Checks**: Builds package sdist/wheel and validates package metadata formatting using `twine check`.
5. **Clean Install Handoff**: Installs the newly built package wheel inside a clean virtual environment and runs:
   * `agent-sudo --version`
   * `agent-sudo doctor`
   * `agent-sudo demo`
   * **JSON-RPC Initialize Handshake**: Pipes a mock MCP initialize request to the `agent-sudo-mcp` entry point to verify server handshake responses.

---

## 2. GitHub Actions Setup (`publish.yml`)

The draft workflow is defined in `.github/workflows/publish.yml`. It supports:
* **Workflow Dispatch (Manual)**: Enables developers to run a dry-run release check on demand with target version inputs.
* **Tag Pushes**: Automatically triggers checks when stable tags matching `v*.*.*` are pushed.

> [!WARNING]
> The workflow defaults to `dry_run: true`. It will **not** publish packages to PyPI or create public GitHub releases automatically. All publishing commands are disabled for review.

---

## 3. Future Work: PyPI Trusted Publishing Setup (OIDC)

When approved to migrate to fully automated publishing:

1. Log in to your publisher account on [PyPI](https://pypi.org).
2. Go to the management console for the `agent-sudo-mcp` package.
3. Navigate to **Publishing** -> **Trusted Publishers** -> **Add Publisher**.
4. Configure the publisher parameters:
   * **GitHub Owner**: `Kisyntra`
   * **Repository**: `Agent_Sudo`
   * **Workflow Name**: `publish.yml`
   * **Environment Name**: `release` (forces the workflow to run within a GitHub environment with manual approvals).
5. On GitHub:
   * Navigate to your repository **Settings** -> **Environments**.
   * Create an environment named `release`.
   * Configure **Required reviewers** to require explicit maintainer approval before OIDC publishing can run.

---

## 4. Release Checklist

Before tag creation or dispatch execution:

- [ ] Ensure all local changes are committed and pushed to `main`.
- [ ] Create a dedicated release notes file at `docs/releases/release_notes_<version_clean>.md` containing the formatted changelog for the tag.
- [ ] Run `python3 scripts/validate_release.py --version <version>` locally to verify version mapping and README integrity.
- [ ] Push the stable tag (e.g. `v0.4.1`) or navigate to **Actions** -> **Secure Package Release** -> **Run workflow** to initiate the dry-run verification gates.
