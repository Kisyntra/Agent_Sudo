from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from agent_sudo import evaluation
from agent_sudo.gateway import main


class RunEvalTests(unittest.TestCase):
    def test_full_ladder_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = evaluation.run_eval(output_dir=tmp)
        self.assertTrue(report.passed)
        self.assertEqual(len(report.steps), 5)
        self.assertTrue(all(s.passed for s in report.steps))

    def test_step1_blocks_without_executing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = evaluation.run_eval(output_dir=tmp)
        step1 = report.steps[0]
        self.assertEqual(step1.detail["decision"], "REQUIRE_STRONG_APPROVAL")
        self.assertFalse(step1.detail["executed"])

    def test_delegation_allows_exactly_once_then_denies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = evaluation.run_eval(output_dir=tmp)
        allowed = report.steps[2].detail
        denied = report.steps[3].detail
        self.assertEqual(allowed["decision"], "ALLOW")
        self.assertEqual(allowed["method"], "DELEGATION")
        self.assertTrue(allowed["executed"])
        self.assertEqual(denied["decision"], "DENY")

    def test_token_usage_increments_to_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = evaluation.run_eval(output_dir=tmp)
        self.assertEqual(report.steps[3].detail["uses"], 1)

    def test_audit_chain_verifies_and_file_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = evaluation.run_eval(output_dir=tmp)
            self.assertTrue(report.steps[4].passed)
            self.assertTrue(report.audit_log.exists())

    def test_default_output_is_a_persisted_temp_dir(self) -> None:
        report = evaluation.run_eval()
        try:
            self.assertTrue(report.audit_log.exists())  # persists after the call
            self.assertIn("agent-sudo-eval-", str(report.audit_log))
        finally:
            # cleanup the persisted temp dir this test created
            import shutil

            shutil.rmtree(report.audit_log.parent, ignore_errors=True)


class EvalCliTests(unittest.TestCase):
    def _run(self, argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(argv)
        return code, out.getvalue()

    def test_cli_exits_zero_and_prints_pass_and_explanation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, out = self._run(["eval", "--output-dir", tmp])
        self.assertEqual(code, 0)
        self.assertIn("Result: PASS", out)
        self.assertIn("Audit log:", out)
        self.assertIn("Next: agent-sudo audit list", out)
        self.assertIn("What you just saw", out)
        # PASS ladder, 5 steps
        self.assertEqual(out.count("PASS"), 6)  # 5 steps + Result line

    def test_cli_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, out = self._run(["eval", "--output-dir", tmp, "--json"])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["result"], "pass")
        self.assertEqual(len(data["steps"]), 5)
        self.assertTrue(data["audit_log"].endswith("audit.jsonl"))
        self.assertNotIn("What you just saw", out)  # machine output stays clean

    def test_failure_path_exits_nonzero(self) -> None:
        # Force a step to fail by stubbing run_eval to report a failed step.
        bad = evaluation.EvalReport(
            steps=[
                evaluation.StepResult(
                    1,
                    "blocked_unsafe_request",
                    "Blocked unsafe request",
                    False,
                    {"decision": "ALLOW", "executed": True},
                ),
            ],
            audit_log=Path("/tmp/nope/audit.jsonl"),
        )
        with mock.patch("agent_sudo.evaluation.run_eval", return_value=bad):
            code, out = self._run(["eval"])
        self.assertEqual(code, evaluation.EXIT_FAIL)
        self.assertIn("Result: FAIL", out)

    def test_internal_error_exits_with_error_code(self) -> None:
        with mock.patch(
            "agent_sudo.evaluation.run_eval", side_effect=OSError("disk full")
        ):
            code, _ = self._run(["eval"])
        self.assertEqual(code, evaluation.EXIT_ERROR)

    def test_does_not_write_to_user_home_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            with mock.patch.dict(os.environ, {"HOME": home}):
                code, _ = self._run(["eval"])
        self.assertEqual(code, 0)
        self.assertFalse((Path(home) / ".agent-sudo").exists())


if __name__ == "__main__":
    unittest.main()
