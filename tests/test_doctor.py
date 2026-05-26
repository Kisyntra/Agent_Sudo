from __future__ import annotations

import io
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stdout
from pathlib import Path

from agent_sudo.doctor import DoctorCheck, doctor_exit_code, format_doctor_checks, run_doctor
from agent_sudo.gateway import main


class DoctorTests(unittest.TestCase):
    def test_doctor_runs_checks(self) -> None:
        checks = run_doctor()
        names = {check.name for check in checks}

        self.assertIn("Python version OK", names)
        self.assertIn("default policy exists", names)
        self.assertIn("audit log writable", names)
        self.assertIn("delegation store writable", names)
        self.assertIn("no personal data in repo", names)

    def test_doctor_exit_code_fails_required_check(self) -> None:
        checks = [DoctorCheck("Python version OK", False, "too old")]

        self.assertEqual(doctor_exit_code(checks), 1)

    def test_doctor_format_contains_status(self) -> None:
        text = format_doctor_checks([DoctorCheck("approval config exists", False, "not initialized")])

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


if __name__ == "__main__":
    unittest.main()
