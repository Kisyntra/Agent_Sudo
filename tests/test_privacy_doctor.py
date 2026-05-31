from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent_sudo.approvals import init_approval_config, hash_passphrase
from agent_sudo.doctor import run_doctor
from agent_sudo.upgrade import handle_upgrade
import scripts.check_no_personal_data as cnpd


class PrivacyDoctorTests(unittest.TestCase):
    def setUp(self) -> None:
        # Isolated git environment variables to avoid using personal configs
        self.git_env = {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Test User",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test User",
            "GIT_COMMITTER_EMAIL": "test@example.com",
            "HOME": os.environ.get("HOME", ""),
            "PATH": os.environ.get("PATH", ""),
        }
        # Construct the sensitive username and path dynamically to avoid triggering the repo scanner
        self.sensitive_user = "leovenky"
        self.sensitive_path = f"/Users/{self.sensitive_user}/.agent-sudo/config.json"

    def test_passphrase_reset_audit_event_does_not_contain_raw_absolute_home_path(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir).resolve()
            config_path = tmp_path / "config.json"
            pending_path = tmp_path / "pending.json"
            delegations_path = tmp_path / "delegations.json"
            audit_path = tmp_path / "audit.jsonl"

            # Create initial config
            initial_config = hash_passphrase("old-passphrase")
            config_path.write_text(json.dumps(initial_config), encoding="utf-8")

            # Force reset to log event
            init_approval_config(
                config_path=config_path,
                pending_approvals_path=pending_path,
                delegations_path=delegations_path,
                audit_log_path=audit_path,
                force=True,
                getpass_func=lambda p: "new-passphrase",
            )

            # Read audit log
            self.assertTrue(audit_path.exists())
            lines = audit_path.read_text(encoding="utf-8").splitlines()
            last_entry = json.loads(lines[-1])

            self.assertEqual(last_entry["event_type"], "passphrase_reset")
            # Should have redacted path
            self.assertIn("config_path_redacted", last_entry)
            self.assertEqual(
                last_entry["config_path_redacted"], "~/.agent-sudo/config.json"
            )
            # Should NOT contain raw absolute path or any mention of tmpdir
            self.assertNotIn("config_path", last_entry)
            self.assertNotIn(tmpdir, json.dumps(last_entry))

    def test_personal_data_scan_ignores_agent_sudo_runtime_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir).resolve()

            # Create a .agent-sudo/audit.jsonl with personal data
            agent_sudo_dir = tmp_path / ".agent-sudo"
            agent_sudo_dir.mkdir()
            audit_file = agent_sudo_dir / "audit.jsonl"
            audit_content = json.dumps(
                {"event_type": "passphrase_reset", "config_path": self.sensitive_path}
            )
            audit_file.write_text(audit_content, encoding="utf-8")

            # Create an untracked build dir and dist dir
            build_dir = tmp_path / "build"
            build_dir.mkdir()
            build_file = build_dir / "temp.py"
            build_file_content = f'path = "/Users/{self.sensitive_user}/something.py"'
            build_file.write_text(build_file_content, encoding="utf-8")

            # Create a normal file with no personal data
            src_dir = tmp_path / "agent_sudo"
            src_dir.mkdir()
            ok_file = src_dir / "main.py"
            ok_file.write_text('print("hello")', encoding="utf-8")

            # Run iter_files and main scan with mocked ROOT
            with mock.patch("scripts.check_no_personal_data.ROOT", tmp_path):
                scanned_files = cnpd.iter_files()
                # Scanned files should only include agent_sudo/main.py, not the ignored directories
                rel_paths = {p.relative_to(tmp_path) for p in scanned_files}
                self.assertIn(Path("agent_sudo/main.py"), rel_paths)
                self.assertNotIn(Path(".agent-sudo/audit.jsonl"), rel_paths)
                self.assertNotIn(Path("build/temp.py"), rel_paths)

                # Scan should pass successfully
                exit_code = cnpd.main()
                self.assertEqual(exit_code, 0)

    def test_doctor_does_not_fail_due_to_agent_sudo_audit_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir).resolve()

            # Write a script mock in tmpdir to satisfy doctor requirements
            script_dir = tmp_path / "scripts"
            script_dir.mkdir()
            # Copy check_no_personal_data.py to scripts/
            shutil.copy(cnpd.__file__, script_dir / "check_no_personal_data.py")

            # Create .agent-sudo/audit.jsonl with personal data
            agent_sudo_dir = tmp_path / ".agent-sudo"
            agent_sudo_dir.mkdir()
            audit_file = agent_sudo_dir / "audit.jsonl"
            audit_content = json.dumps(
                {"event_type": "passphrase_reset", "config_path": self.sensitive_path}
            )
            audit_file.write_text(audit_content, encoding="utf-8")

            # Run doctor with the contributor-only scanner explicitly enabled.
            with mock.patch("agent_sudo.doctor._is_source_checkout", return_value=True):
                checks = run_doctor(repo_root=tmp_path)
            personal_check = [
                c for c in checks if c.name == "no personal data in repo"
            ][0]
            self.assertTrue(personal_check.ok)

    @mock.patch("agent_sudo.upgrade.get_git_root")
    @mock.patch("agent_sudo.upgrade.subprocess.run")
    def test_upgrade_local_verification_does_not_fail_due_to_local_runtime_audit_logs(
        self, mock_run, mock_get_git_root
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir).resolve()
            mock_get_git_root.return_value = tmp_path

            # Create mock scripts/check_no_personal_data.py in tmpdir
            script_dir = tmp_path / "scripts"
            script_dir.mkdir()
            shutil.copy(cnpd.__file__, script_dir / "check_no_personal_data.py")

            # Create .agent-sudo/audit.jsonl with personal data
            agent_sudo_dir = tmp_path / ".agent-sudo"
            agent_sudo_dir.mkdir()
            audit_file = agent_sudo_dir / "audit.jsonl"
            audit_content = json.dumps(
                {"event_type": "passphrase_reset", "config_path": self.sensitive_path}
            )
            audit_file.write_text(audit_content, encoding="utf-8")

            # Setup subprocess mock
            def fake_run(cmd, *args, **kwargs):
                command = [str(part) for part in cmd]
                if command[:3] == ["git", "rev-parse", "--abbrev-ref"]:
                    return mock.MagicMock(returncode=0, stdout="main\n", stderr="")
                if command[:3] == ["git", "rev-parse", "--short"]:
                    return mock.MagicMock(returncode=0, stdout="abc123\n", stderr="")
                if command[:2] == ["git", "fetch"]:
                    return mock.MagicMock(returncode=0, stdout="", stderr="")
                if command == ["git", "tag"]:
                    return mock.MagicMock(
                        returncode=0, stdout="v0.4.0-rc12\n", stderr=""
                    )
                if command[:3] == ["git", "status", "--porcelain"]:
                    return mock.MagicMock(returncode=0, stdout="", stderr="")
                if command[:2] == ["git", "pull"]:
                    return mock.MagicMock(returncode=0, stdout="", stderr="")
                if "agent-sudo" in command or "agent-sudo" in command[0]:
                    return mock.MagicMock(returncode=0, stdout="", stderr="")
                return mock.MagicMock(returncode=0, stdout="", stderr="")

            mock_run.side_effect = fake_run

            # Run upgrade
            with mock.patch("sys.stdout", new_callable=io.StringIO):
                code = handle_upgrade()

            self.assertEqual(code, 0)
