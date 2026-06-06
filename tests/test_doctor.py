from __future__ import annotations

import io
import json
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stdout
from pathlib import Path

from agent_sudo.doctor import (
    DoctorCheck,
    doctor_exit_code,
    format_doctor_checks,
    run_doctor,
)
from agent_sudo.gateway import main


class DoctorTests(unittest.TestCase):
    def test_doctor_runs_checks(self) -> None:
        checks = run_doctor()
        names = {check.name for check in checks}

        self.assertIn("Python version OK", names)
        self.assertIn("default policy exists", names)
        self.assertIn("audit log writable", names)
        self.assertIn("delegation store writable", names)
        # doctor reports user readiness only — no contributor/repo hygiene scan.
        self.assertNotIn("no personal data in repo", names)

    def test_doctor_never_runs_repo_hygiene_scan(self) -> None:
        # Even from a source checkout that contains the scanner, doctor must
        # not run it or surface its output to evaluators.
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir).resolve()
            script_dir = tmp_path / "scripts"
            script_dir.mkdir()
            (script_dir / "check_no_personal_data.py").write_text(
                "raise SystemExit(1)\n",
                encoding="utf-8",
            )
            venv_dir = tmp_path / "test_venv"
            venv_dir.mkdir()
            (venv_dir / "example.txt").write_text(
                "/Users/username/Library/Application Support/SuperApp",
                encoding="utf-8",
            )

            checks = run_doctor(repo_root=tmp_path)
            names = {check.name for check in checks}

            self.assertNotIn("no personal data in repo", names)

    def test_doctor_exit_code_fails_required_check(self) -> None:
        checks = [DoctorCheck("Python version OK", False, "too old")]

        self.assertEqual(doctor_exit_code(checks), 1)

    def test_doctor_format_contains_status(self) -> None:
        text = format_doctor_checks(
            [DoctorCheck("approval config exists", False, "not initialized")]
        )

        self.assertIn("WARN: approval config exists", text)

    def test_doctor_command_prints_checks(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["doctor"])

        self.assertIn(code, {0, 1})
        self.assertIn("Python version OK", output.getvalue())

    def test_setup_command_is_dry_run_checklist(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["setup", "codex"])

        self.assertEqual(code, 0)
        self.assertIn("dry-run only", output.getvalue())
        self.assertIn("Verify with:", output.getvalue())

    def test_doctor_output_before_initialization(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            non_existent = Path(tmpdir) / "config.json"
            with unittest.mock.patch("agent_sudo.doctor.CONFIG_PATH", non_existent):
                output = io.StringIO()
                with redirect_stdout(output):
                    main(["doctor"])

                self.assertIn("APPROVALS: NOT INITIALIZED", output.getvalue())
                self.assertIn("agent-sudo init-approval", output.getvalue())

    def test_doctor_output_after_initialization(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            existent = Path(tmpdir) / "config.json"
            existent.write_text("{}", encoding="utf-8")
            with unittest.mock.patch("agent_sudo.doctor.CONFIG_PATH", existent):
                output = io.StringIO()
                with redirect_stdout(output):
                    main(["doctor"])

                self.assertNotIn("APPROVALS: NOT INITIALIZED", output.getvalue())
                self.assertIn("OK: approval config exists", output.getvalue())

    def test_approve_without_initialization(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            non_existent = Path(tmpdir) / "config.json"
            with unittest.mock.patch("agent_sudo.gateway.CONFIG_PATH", non_existent):
                err = io.StringIO()
                with unittest.mock.patch("sys.stderr", err):
                    code = main(["approve", "some-id"])

                self.assertEqual(code, 1)
                self.assertIn("approval system not initialized", err.getvalue())
                self.assertIn("agent-sudo init-approval", err.getvalue())


class DoctorBroadDelegationTests(unittest.TestCase):
    def _broad_token(self) -> dict:
        return {
            "token_id": "broad-1",
            "actor": "mcp-client",
            "allowed_actions": ["write_file"],
            "allowed_paths": ["*"],
            "denied_actions": [],
            "expires_at": "2026-06-06T05:00:00Z",
            "max_uses": 10,
            "uses": 0,
            "revoked": False,
            "critical": False,
            "created_at": "2026-06-06T01:00:00Z",
        }

    def _run_with_store(self, tokens: list) -> list[DoctorCheck]:
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "delegations.json"
            store_path.write_text(json.dumps(tokens), encoding="utf-8")
            with unittest.mock.patch(
                "agent_sudo.doctor.default_delegations_path",
                return_value=store_path,
            ):
                return run_doctor()

    def test_warns_when_broad_delegation_present(self) -> None:
        checks = self._run_with_store([self._broad_token()])
        scope = next(c for c in checks if c.name == "delegation scope")
        self.assertFalse(scope.ok)
        self.assertIn("broad", scope.detail)
        self.assertIn("broad-1", scope.detail)
        # WARN only — must not flip the doctor exit code to failure.
        self.assertEqual(doctor_exit_code(checks), 0)

    def test_ok_when_no_broad_delegation(self) -> None:
        narrow = self._broad_token()
        narrow["allowed_paths"] = ["/ws/a.txt"]
        checks = self._run_with_store([narrow])
        scope = next(c for c in checks if c.name == "delegation scope")
        self.assertTrue(scope.ok)


if __name__ == "__main__":
    unittest.main()
