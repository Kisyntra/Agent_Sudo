from __future__ import annotations

import io
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

from agent_sudo.gateway import main
from agent_sudo.upgrade import version_key, handle_upgrade


class UpgradeTests(unittest.TestCase):
    def test_version_key_parsing(self) -> None:
        self.assertEqual(version_key("v0.3.4-beta"), (0, 3, 4))
        self.assertEqual(version_key("v0.4.0-rc1"), (0, 4, 0, 1))
        self.assertEqual(version_key("v0.12.0"), (0, 12, 0))
        self.assertEqual(version_key("0.3.3b0"), (0, 3, 3, 0))

    @unittest.mock.patch("agent_sudo.upgrade.get_git_root")
    def test_check_in_non_git_directory(self, mock_get_git_root) -> None:
        mock_get_git_root.return_value = None

        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["upgrade-local", "--check"])

        self.assertEqual(code, 1)
        self.assertIn("This installation is not inside a git repository.", err.getvalue())
        self.assertIn("pip install --upgrade agent-sudo", err.getvalue())

    @unittest.mock.patch("agent_sudo.upgrade.get_git_root")
    @unittest.mock.patch("agent_sudo.upgrade.is_working_tree_dirty")
    @unittest.mock.patch("subprocess.run")
    def test_dirty_working_tree_refuses_upgrade(
        self, mock_run, mock_is_dirty, mock_get_git_root
    ) -> None:
        mock_get_git_root.return_value = Path("/tmp/mock-repo")
        mock_is_dirty.return_value = True

        # Mock Git commands that run before status checks
        mock_run.return_value = unittest.mock.MagicMock(returncode=0, stdout="main")

        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["upgrade-local"])

        self.assertEqual(code, 1)
        self.assertIn("Git working tree has uncommitted changes", err.getvalue())
        self.assertIn("Please commit or stash your changes, or pass --allow-dirty", err.getvalue())

    @unittest.mock.patch("agent_sudo.upgrade.get_git_root")
    @unittest.mock.patch("agent_sudo.upgrade.is_working_tree_dirty")
    @unittest.mock.patch("subprocess.run")
    def test_state_preservation_warning_appears(
        self, mock_run, mock_is_dirty, mock_get_git_root
    ) -> None:
        mock_get_git_root.return_value = Path("/tmp/mock-repo")
        mock_is_dirty.return_value = False

        # Set up mock run outputs
        mock_run.return_value = unittest.mock.MagicMock(returncode=0, stdout="v0.3.5-beta")

        out = io.StringIO()
        with redirect_stdout(out):
            # Just do check to avoid actual pull/reinstall subprocesses running
            code = main(["upgrade-local", "--check"])

        self.assertEqual(code, 0)
        self.assertIn("Local state, audit logs, and delegations under ~/.agent-sudo will be preserved", out.getvalue())

    def test_does_not_touch_agent_sudo_dir(self) -> None:
        # Confirm that handle_upgrade does not attempt to access user home config path ~/.agent-sudo/ in tests
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_home = Path(tmpdir)
            with unittest.mock.patch("pathlib.Path.home", return_value=fake_home):
                with unittest.mock.patch("agent_sudo.upgrade.get_git_root") as mock_git_root:
                    mock_git_root.return_value = None
                    err = io.StringIO()
                    with redirect_stderr(err):
                        handle_upgrade(check_only=True)

            # Assert that no file or folder named .agent-sudo is created under the fake home directory
            agent_sudo_dir = fake_home / ".agent-sudo"
            self.assertFalse(agent_sudo_dir.exists())


if __name__ == "__main__":
    unittest.main()
