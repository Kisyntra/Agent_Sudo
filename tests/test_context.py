from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent_sudo.context import detect_runtime_context
from agent_sudo.gateway import main
from agent_sudo.mcp_gateway import MCPGateway
from agent_sudo.gateway import PermissionGateway
from agent_sudo.policy import load_default_policy
from agent_sudo.models import Decision


class RuntimeContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_default_policy()
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

    def test_git_repository_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir).resolve()
            # Initialize git repo
            subprocess.run(
                ["git", "init"],
                cwd=tmp_path,
                env=self.git_env,
                capture_output=True,
                check=True,
            )
            # Create a dummy commit to have a branch
            subprocess.run(
                ["git", "checkout", "-b", "main"],
                cwd=tmp_path,
                env=self.git_env,
                capture_output=True,
                check=False,
            )
            # Make a commit
            dummy_file = tmp_path / "dummy.txt"
            dummy_file.write_text("dummy", encoding="utf-8")
            subprocess.run(
                ["git", "add", "dummy.txt"],
                cwd=tmp_path,
                env=self.git_env,
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "initial commit"],
                cwd=tmp_path,
                env=self.git_env,
                capture_output=True,
                check=True,
            )

            # Detect context
            ctx = detect_runtime_context(cwd=tmp_path)
            self.assertEqual(ctx.repo_root, str(tmp_path))
            self.assertEqual(ctx.git_branch, "main")
            self.assertTrue(ctx.workspace_detected)
            self.assertFalse(ctx.running_from_root)

    def test_non_git_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir).resolve()
            ctx = detect_runtime_context(cwd=tmp_path)
            self.assertIsNone(ctx.repo_root)
            self.assertIsNone(ctx.git_branch)
            self.assertFalse(ctx.workspace_detected)
            self.assertFalse(ctx.running_from_root)

    def test_filesystem_root(self) -> None:
        # Save stderr
        original_stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            ctx = detect_runtime_context("/")
            # filesystem root should have running_from_root = True
            self.assertTrue(ctx.running_from_root)
            # Stderr should contain root warning
            warning_out = sys.stderr.getvalue()
            self.assertIn("Warning: running from root directory", warning_out)
        finally:
            sys.stderr = original_stderr

    def test_detached_head(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir).resolve()
            # Initialize git repo
            subprocess.run(
                ["git", "init"],
                cwd=tmp_path,
                env=self.git_env,
                capture_output=True,
                check=True,
            )
            dummy_file = tmp_path / "dummy.txt"
            dummy_file.write_text("dummy", encoding="utf-8")
            subprocess.run(
                ["git", "add", "dummy.txt"],
                cwd=tmp_path,
                env=self.git_env,
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "initial commit"],
                cwd=tmp_path,
                env=self.git_env,
                capture_output=True,
                check=True,
            )

            # Get commit hash
            completed = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=tmp_path,
                env=self.git_env,
                capture_output=True,
                text=True,
                check=True,
            )
            commit_sha = completed.stdout.strip()
            short_sha = commit_sha[:7]

            # Checkout commit directly (detached HEAD)
            subprocess.run(
                ["git", "checkout", commit_sha],
                cwd=tmp_path,
                env=self.git_env,
                capture_output=True,
                check=True,
            )

            # Detect context
            ctx = detect_runtime_context(cwd=tmp_path)
            self.assertEqual(ctx.repo_root, str(tmp_path))
            self.assertIsNotNone(ctx.git_branch)
            self.assertIn("detached", ctx.git_branch)
            self.assertIn(short_sha, ctx.git_branch)

    def test_missing_git_executable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir).resolve()
            with mock.patch("shutil.which", return_value=None):
                ctx = detect_runtime_context(cwd=tmp_path)
                self.assertIsNone(ctx.repo_root)
                self.assertIsNone(ctx.git_branch)
                self.assertFalse(ctx.workspace_detected)
                self.assertIn("git executable not found", ctx.warnings)

    def test_invalid_path(self) -> None:
        # Non-existent path
        non_existent = "/non/existent/path/for/agent_sudo/test"
        ctx = detect_runtime_context(non_existent)
        self.assertFalse(ctx.workspace_detected)
        self.assertTrue(any("does not exist" in w for w in ctx.warnings))

        # Test file path (resolves to parent directory)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir).resolve()
            tmp_file = tmp_path / "test.txt"
            tmp_file.write_text("hello", encoding="utf-8")

            ctx = detect_runtime_context(tmp_file)
            self.assertEqual(ctx.cwd, str(tmp_path))

    def test_cli_context_command(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", stderr):
            exit_code = main(["context"])
        
        self.assertEqual(exit_code, 0)
        output_json = json.loads(stdout.getvalue())
        self.assertIn("cwd", output_json)
        self.assertIn("repo_root", output_json)
        self.assertIn("git_branch", output_json)
        self.assertIn("workspace_detected", output_json)
        self.assertIn("running_from_root", output_json)

    def test_mcp_get_runtime_context_tool(self) -> None:
        gateway = PermissionGateway(self.policy)
        mcp_gateway = MCPGateway(gateway)
        
        result = mcp_gateway.dispatch(
            {
                "actor": "mcp-client",
                "source": "user",
                "tool": "get_runtime_context",
                "action": "get_runtime_context",
                "target": "get_runtime_context",
            }
        )
        
        self.assertTrue(result.executed)
        self.assertEqual(result.gateway_result.decision, Decision.ALLOW)
        
        # Parse stdout JSON
        ctx_dict = json.loads(result.stdout)
        self.assertIn("cwd", ctx_dict)
        self.assertIn("repo_root", ctx_dict)
        self.assertIn("git_branch", ctx_dict)
        self.assertIn("workspace_detected", ctx_dict)
        self.assertIn("running_from_root", ctx_dict)
