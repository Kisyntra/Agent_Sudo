from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from agent_sudo.audit_trace import (
    _causes_in,
    _token_segment,
    build_trace,
    resolve_token,
    status_of,
)
from agent_sudo.gateway import main

TOK_EXH = "d281e64f-d995-4361-ba2b-09e1a3386c75"  # exhausted, consumed once
TOK_REV = "613939a9-529c-4bee-ae99-08d1a1ef6b32"  # revoked, never consumed
TOK_OK = "66ef0ba1-2924-4aaa-bbbb-cccccccccccc"  # happy, uses 3/4


def _decision(decision: str, action: str, target: str, reason: str) -> dict:
    return {
        "timestamp": "2026-06-01T21:56:01Z",
        "event_type": "gateway_decision",
        "decision": decision,
        "reason": reason,
        "request": {
            "actor": "hermes",
            "tool": "terminal",
            "action": action,
            "target": target,
            "provenance": {"origin_type": "AGENT_INTERNAL"},
        },
    }


def _entries() -> list[dict]:
    multi = (
        f"delegation token {TOK_EXH} mismatched: token exhausted, "
        "action mismatch: expected action in ['run_shell_command'], "
        "actual action 'write_file', path mismatch: expected path scope in "
        "['pwd'], actual target '/tmp/x'; "
        f"delegation token {TOK_REV} mismatched: token revoked"
    )
    return [
        _decision(
            "ALLOW",
            "run_shell_command",
            "pwd",
            f"delegated by {TOK_EXH}: dogfood P0 serial terminal pwd",
        ),
        _decision(
            "DENY",
            "run_shell_command",
            "pwd",
            f"delegation token {TOK_EXH} mismatched: token exhausted",
        ),
        _decision("DENY", "write_file", "/tmp/x", multi),
        _decision(
            "ALLOW",
            "edit_file",
            "/bridge.py",
            f"delegated by {TOK_OK}: Hermes bridge edit proof",
        ),
    ]


def _delegations() -> list[dict]:
    return [
        {
            "token_id": TOK_EXH,
            "actor": "hermes",
            "allowed_actions": ["run_shell_command"],
            "allowed_paths": ["pwd"],
            "max_uses": 1,
            "uses": 1,
            "created_at": "2026-06-01T21:55:47Z",
            "expires_at": "2026-06-01T22:00:47Z",
            "revoked": False,
            "reason": "dogfood P0 serial terminal pwd",
        },
        {
            "token_id": TOK_REV,
            "actor": "hermes",
            "allowed_actions": ["run_shell_command"],
            "allowed_paths": ["pwd"],
            "max_uses": 1,
            "uses": 0,
            "created_at": "2026-06-01T23:04:09Z",
            "expires_at": "2026-06-02T01:04:09Z",
            "revoked": True,
            "reason": "Test 4a: terminal scope for pwd",
        },
        {
            "token_id": TOK_OK,
            "actor": "hermes",
            "allowed_actions": ["edit_file"],
            "allowed_paths": ["/bridge.py"],
            "max_uses": 4,
            "uses": 3,
            "created_at": "2026-06-02T17:26:27Z",
            "expires_at": "2099-01-01T00:00:00Z",
            "revoked": False,
            "reason": "Hermes bridge edit proof",
        },
    ]


class SegmentAndCauseTests(unittest.TestCase):
    def test_segment_isolates_this_tokens_causes(self) -> None:
        # The multi-token reason must NOT cross-attribute causes.
        multi = _entries()[2]["reason"]
        exh_seg = _token_segment(multi, TOK_EXH)
        rev_seg = _token_segment(multi, TOK_REV)
        self.assertIn("token exhausted", exh_seg)
        self.assertNotIn("token revoked", exh_seg)
        self.assertIn("token revoked", rev_seg)
        self.assertNotIn("token exhausted", rev_seg)

    def test_causes_keyword_based(self) -> None:
        seg = _token_segment(_entries()[2]["reason"], TOK_EXH)
        causes = _causes_in(seg)
        self.assertIn("token exhausted", causes)
        self.assertIn("action mismatch", causes)
        self.assertIn("path mismatch", causes)
        self.assertNotIn("token revoked", causes)


class StatusTests(unittest.TestCase):
    def test_revoked(self) -> None:
        self.assertEqual(status_of(_delegations()[1])[0], "REVOKED")

    def test_exhausted(self) -> None:
        self.assertEqual(status_of(_delegations()[0])[0], "EXHAUSTED")

    def test_active(self) -> None:
        self.assertEqual(status_of(_delegations()[2])[0], "ACTIVE")

    def test_unknown_when_no_metadata(self) -> None:
        self.assertEqual(status_of(None)[0], "UNKNOWN")


class ResolveTests(unittest.TestCase):
    def test_exact(self) -> None:
        tid, cands = resolve_token(TOK_EXH, _entries(), _delegations())
        self.assertEqual(tid, TOK_EXH)
        self.assertEqual(cands, [])

    def test_unique_prefix(self) -> None:
        tid, _ = resolve_token("d281e64f", _entries(), _delegations())
        self.assertEqual(tid, TOK_EXH)

    def test_not_found(self) -> None:
        tid, cands = resolve_token("beadface", _entries(), _delegations())
        self.assertIsNone(tid)
        self.assertEqual(cands, [])

    def test_ambiguous_prefix(self) -> None:
        # prefix "6" matches 66ef0ba1 (TOK_OK), 613939a9 (TOK_REV), and a sibling
        delegs = _delegations() + [{"token_id": "6e9db3ca-aaaa"}]
        tid, cands = resolve_token("6", _entries(), delegs)
        self.assertIsNone(tid)
        self.assertEqual(len(cands), 3)
        self.assertTrue(all(c.startswith("6") for c in cands))


class BuildTraceTests(unittest.TestCase):
    def test_counts_consume_and_denials(self) -> None:
        trace = build_trace(TOK_EXH, _entries(), _delegations()[0])
        self.assertEqual(trace["counts"]["observed_consumes"], 1)
        self.assertEqual(trace["counts"]["observed_denials"], 2)
        self.assertEqual(trace["counts"]["references"], 3)

    def test_causes_attributed_only_to_this_token(self) -> None:
        trace = build_trace(TOK_EXH, _entries(), _delegations()[0])
        self.assertNotIn("token revoked", trace["inferred_causes"])
        self.assertEqual(trace["inferred_causes"]["token exhausted"], 2)

    def test_revoked_token_has_zero_consumes(self) -> None:
        trace = build_trace(TOK_REV, _entries(), _delegations()[1])
        self.assertEqual(trace["counts"]["observed_consumes"], 0)
        self.assertEqual(trace["status"], "REVOKED")


class CliTraceTests(unittest.TestCase):
    def _write(self, tmpdir: str) -> tuple[Path, Path]:
        log = Path(tmpdir) / "audit.jsonl"
        with log.open("w", encoding="utf-8") as fh:
            for e in _entries():
                fh.write(json.dumps(e) + "\n")
        delegs = Path(tmpdir) / "delegations.json"
        delegs.write_text(json.dumps(_delegations()))
        return log, delegs

    def test_trace_exhausted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log, _ = self._write(tmp)  # delegations.json sits beside the log
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(["audit", "trace", "d281e64f", str(log)])
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("EXHAUSTED", out)
        self.assertIn("observed in log:", out)
        self.assertIn("1 observed consumes", out)
        self.assertIn("reason cites token exhausted", out)
        # never overclaims intended-token / exact causality wording
        self.assertNotIn("the agent tried", out)

    def test_trace_json_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log, delegs = self._write(tmp)
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(
                    [
                        "audit",
                        "trace",
                        TOK_EXH,
                        str(log),
                        "--delegations-file",
                        str(delegs),
                        "--json",
                    ]
                )
        self.assertEqual(code, 0)
        obj = json.loads(buf.getvalue())
        self.assertEqual(obj["token_id"], TOK_EXH)
        self.assertEqual(obj["counts"]["observed_denials"], 2)
        self.assertEqual(obj["status"], "EXHAUSTED")

    def test_trace_unknown_token_exits_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log, _ = self._write(tmp)
            err = io.StringIO()
            with redirect_stderr(err):
                code = main(["audit", "trace", "beadface", str(log)])
        self.assertEqual(code, 1)
        self.assertIn("No delegation found", err.getvalue())

    def test_trace_ambiguous_prefix_exits_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "audit.jsonl"
            with log.open("w") as fh:
                for e in _entries():
                    fh.write(json.dumps(e) + "\n")
            delegs = Path(tmp) / "delegations.json"
            delegs.write_text(
                json.dumps(_delegations() + [{"token_id": "6e9db3ca-aaaa"}])
            )
            err = io.StringIO()
            with redirect_stderr(err):
                code = main(["audit", "trace", "6", str(log)])
        self.assertEqual(code, 1)
        self.assertIn("ambiguous", err.getvalue())

    def test_trace_does_not_mutate_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log, delegs = self._write(tmp)
            before = (log.read_bytes(), delegs.read_bytes())
            with redirect_stdout(io.StringIO()):
                main(["audit", "trace", TOK_EXH, str(log)])
            after = (log.read_bytes(), delegs.read_bytes())
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
