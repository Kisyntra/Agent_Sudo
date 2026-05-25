from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

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


if __name__ == "__main__":
    unittest.main()
