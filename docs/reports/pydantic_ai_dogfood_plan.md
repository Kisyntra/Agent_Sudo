# Implementation Plan — Real Deterministic PydanticAI Dogfood Demo

**Type:** Plan only. No implementation in this document.
**Goal:** Replace the current `examples/pydantic_ai/` snippet with a real, deterministic, offline, CI-runnable demo that shows the full library-integration path:

```
PydanticAI agent → PermissionGateway → real local file action → approval/delegation → audit log → audit verification
```

**Note:** the LLM is a deterministic test double; the gateway decision, delegation, file I/O, and audit verification are real. The README states this plainly.

---

## 1. Exact PydanticAI test-model approach

Use **`FunctionModel`** (from `pydantic_ai.models.function`), not `TestModel`.

- `TestModel` calls every tool once with *auto-generated* arguments — it cannot target a specific file path, so it can't drive scripted scenarios. Good for smoke tests, wrong here.
- `FunctionModel(func)` lets us write `func(messages, info) -> ModelResponse` that returns an exact `ToolCallPart(tool_name=..., args={...})` based on the prompt, then a final `TextPart` after the tool result. Fully deterministic, offline, no API key.

Sketch (illustrative, not final):
```python
from pydantic_ai import Agent
from pydantic_ai.models.function import FunctionModel, AgentInfo
from pydantic_ai.messages import ModelResponse, ToolCallPart, TextPart, ModelRequest

def scripted_model(messages, info: AgentInfo) -> ModelResponse:
    # First turn: emit the tool call dictated by the scenario prompt.
    # Second turn (tool result present): emit a final text part to end the run.
    last = messages[-1]
    if not _has_tool_return(last):
        tool, args = _SCENARIO[_prompt_text(messages)]
        return ModelResponse(parts=[ToolCallPart(tool_name=tool, args=args)])
    return ModelResponse(parts=[TextPart("done")])

agent = Agent(FunctionModel(scripted_model))
```
Each scenario is one `agent.run_sync(prompt)`; the model maps prompt → exact tool+args. This is standard PydanticAI testing practice (their own docs use `FunctionModel` this way), so it's an idiomatic example, not a hack.

---

## 2. Approval provider vs delegation token for the non-interactive demo

**Use a delegation token as the primary mechanism**, and *also* show the un-delegated attempt being held.

Rationale:
- A delegation token is a **real product feature** (scoped, TTL-limited, use-limited pre-authorization). It is deterministic and non-interactive *without faking a human*. An auto-approve `ApprovalProvider` would be a "click yes for you" stub — exactly the kind of fake we're trying to remove.
- `ApproveAllProvider` only exists in the test suite, not the package — using it would import test code into an example.

So scenario 2 has two halves:
- **2a (held):** sensitive `write_file` with **no** delegation → gateway returns `REQUIRE_APPROVAL` → the gate **blocks** (raises), proving we never treat `REQUIRE_APPROVAL` as `ALLOW`.
- **2b (delegated):** issue `DelegationStore.create(actor=..., allowed_actions=["write_file"], allowed_paths=[tmp_dir], ttl_seconds=..., max_uses=1)`; the gateway (constructed with that `delegation_store`) authorizes the in-scope write → `ALLOW` → the tool performs a **real** `Path.write_text`. The audit entry records `method=delegation`.

(Note for the COO/PM reading: this doubles as a live demo of delegation, our strongest differentiator.)

---

## 3. Exact files changed

| File | Change |
|---|---|
| `examples/pydantic_ai/example.py` | **Full rewrite** (~150–180 lines): real `Agent`+`FunctionModel`, 3 tools doing real temp-dir file ops, gateway with temp `AuditLogger` + temp `DelegationStore`, 4 scenarios, ends with audit verification. |
| `examples/pydantic_ai/README.md` | **Rewrite**: what it proves, a note that the model is a test double and the gateway/delegation/audit path is real, how to run, expected output. |
| `pyproject.toml` | Add optional extra (see §4). |
| `tests/test_example_pydantic_ai.py` | **New**: `pytest.importorskip("pydantic_ai")`, runs each scenario function and asserts real outcomes. |
| `.github/workflows/*` (CI) | Add a step/job that installs `.[examples]` and runs the example + its test (see §6). |
| `CHANGELOG.md` | One line under Unreleased. |

No changes to `agent_sudo/` engine code. No architecture change.

---

## 4. Does pyproject need an optional dependency extra?

**Yes.** Add:
```toml
[project.optional-dependencies]
examples = ["pydantic-ai>=1.0"]
```
Critically, this keeps the **zero-runtime-dependency** promise of `agent-sudo-mcp` intact — `pydantic-ai` is an *examples/dev* extra, never a runtime dependency of the package. Pin a floor (`>=1.0`) and rely on `FunctionModel`/`ToolCallPart` which are stable public testing APIs. (Confirmed available in the installed `pydantic-ai 1.103.0`.)

---

## 5. How the demo is run

```bash
pip install -e ".[examples]"      # or: pipx run --spec ".[examples]" ...
python examples/pydantic_ai/example.py
```
It prints each scenario's decision and real effect, then a final `audit chain verified: N records`. It exits non-zero if any scenario deviates (e.g. a blocked action somehow executed, or the audit chain fails to verify), so it doubles as a self-check.

All state is confined to a `tempfile.TemporaryDirectory()` — the demo **must not** touch `~/.agent-sudo` (point both `AuditLogger(tmp/"audit.jsonl")` and `DelegationStore(tmp/"delegations.json")` at temp paths). This avoids polluting the user's real audit log / delegations.

---

## 6. How it is tested in CI

Two layers, preserving the dependency-free core:

1. **`tests/test_example_pydantic_ai.py`** guarded by `pytest.importorskip("pydantic_ai")`. With the extra absent (the current core CI job), it is **skipped** — so it never breaks the existing dependency-free suite. It asserts: scenario 1 returns the real file content; scenario 2b actually created the file on disk; scenario 2a and 3 raised (no execution); `verify_audit_log` returns `(True, ...)` and the expected number of records.
2. **A CI step/job** that runs `pip install -e ".[examples]"` then `python -m pytest tests/test_example_pydantic_ai.py` **and** `python examples/pydantic_ai/example.py` (the script's own self-check). This can be a new step in the existing CI workflow or a small separate job to keep the heavy install isolated.

Determinism guarantees for CI: no network, no API key, no time-based assertions (audit timestamps are written but never asserted on), temp dirs only.

---

## 7. README / docs wording changes

- **`examples/pydantic_ai/README.md`** — rewrite to: (a) note that the model is deterministic and the gateway/delegation/audit path is real; (b) describe the 4 scenarios; (c) `pip install -e ".[examples]"` + run; (d) expected output incl. the final audit verification line.
- **Root `README.md`** — under "Supported Framework Examples" / the Path 1 (library) section, point to this as **the canonical, runnable end-to-end dogfood** ("agent → gateway → delegation → audit, verified — runs offline").
- **`CHANGELOG.md`** — Unreleased: "Replace the PydanticAI example with a real, deterministic, offline end-to-end demo (agent → gateway → delegation → audited + verified)."
- Optional: a one-line pointer from `docs/examples/langgraph.md` noting PydanticAI is the canonical reference, LangGraph follows the same pattern.

---

## 8. Risks / limitations

- **Heavy dependency tree.** `pydantic-ai` pulls `pydantic`, `httpx`, etc. Mitigation: optional `examples` extra only; never a runtime dep; CI installs it in an isolated step. The zero-runtime-dep promise is preserved.
- **Test-double model, not a real LLM.** Intentional (offline/deterministic), but the README must state it clearly so the example isn't mistaken for proof that a *real* model behaves well — it proves the **integration and enforcement path**, not model behavior.
- **PydanticAI API drift.** `FunctionModel`/message-part shapes are public but evolving across majors. Mitigation: floor-pin `>=1.0`, and the `importorskip` guard means a future incompatibility degrades to a skipped test, not a red core suite. (A follow-up could pin an upper bound if drift bites.)
- **File-state hygiene.** Must route audit + delegation to temp paths; a mistake here would write into the user's real `~/.agent-sudo`. Covered by using `TemporaryDirectory` and explicit path args; the test asserts nothing is written outside tmp.
- **Scope discipline.** This is an example + one test + an extra + docs. No engine changes, no new runtime deps, no approval-UX changes. If it starts growing into "a PydanticAI middleware library," stop and reconsider — that's a separate decision.

---

## Suggested PR shape

- **Title:** `examples: real deterministic PydanticAI dogfood (agent → gateway → delegation → audited + verified)`
- **Commits:** (1) pyproject extra; (2) example.py + README rewrite; (3) test + CI step; (4) root README/CHANGELOG pointers.
- **Verification before opening:** `pip install -e ".[examples]"`, run the example (self-check passes), run the new test, full suite + ruff, personal-data scan, and confirm nothing was written under `~/.agent-sudo`.
