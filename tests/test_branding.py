from __future__ import annotations

import io
import os
import unittest
from contextlib import redirect_stderr
from unittest import mock

from agent_sudo import __version_label__, branding
from agent_sudo.gateway import main


class _TTY(io.StringIO):
    """StringIO that reports as an interactive terminal."""

    def isatty(self) -> bool:
        return True


# Force the "interactive, not CI, color allowed" environment deterministically:
# empty strings are treated as unset by branding._env_set.
_INTERACTIVE_ENV = {"CI": "", "NO_COLOR": "", "AGENT_SUDO_NO_BANNER": ""}


class WordmarkContentTests(unittest.TestCase):
    def test_wordmark_is_one_compact_line_with_version_and_tagline(self) -> None:
        text = branding.wordmark(color=False)
        self.assertEqual(text.count("\n"), 0)  # single line, no ASCII block
        self.assertIn("Agent_Sudo", text)
        self.assertIn(__version_label__, text)
        self.assertIn("Authorization", text)
        self.assertLess(len(text), 80)  # fits a standard terminal width

    def test_color_adds_ansi_and_no_color_strips_it(self) -> None:
        self.assertIn("\033[", branding.wordmark(color=True))
        self.assertNotIn("\033[", branding.wordmark(color=False))
        with mock.patch.dict(os.environ, {"NO_COLOR": "1"}):
            self.assertNotIn("\033[", branding.wordmark())


class WordmarkGatingTests(unittest.TestCase):
    def test_shown_on_tty_when_not_ci(self) -> None:
        with mock.patch.dict(os.environ, _INTERACTIVE_ENV):
            self.assertTrue(branding.should_show_wordmark(_TTY()))

    def test_suppressed_in_ci(self) -> None:
        with mock.patch.dict(os.environ, {**_INTERACTIVE_ENV, "CI": "true"}):
            self.assertFalse(branding.should_show_wordmark(_TTY()))

    def test_suppressed_by_explicit_opt_out(self) -> None:
        with mock.patch.dict(
            os.environ, {**_INTERACTIVE_ENV, "AGENT_SUDO_NO_BANNER": "1"}
        ):
            self.assertFalse(branding.should_show_wordmark(_TTY()))

    def test_suppressed_on_non_tty(self) -> None:
        with mock.patch.dict(os.environ, _INTERACTIVE_ENV):
            self.assertFalse(branding.should_show_wordmark(io.StringIO()))

    def test_print_wordmark_respects_gating(self) -> None:
        with mock.patch.dict(os.environ, _INTERACTIVE_ENV):
            tty = _TTY()
            self.assertTrue(branding.print_wordmark(tty))
            self.assertIn("Agent_Sudo", tty.getvalue())

            plain = io.StringIO()  # not a tty
            self.assertFalse(branding.print_wordmark(plain))
            self.assertEqual(plain.getvalue(), "")


class WordmarkCommandIntegrationTests(unittest.TestCase):
    def _run_with_stderr(self, argv, *, tty: bool, extra_env=None, stdin_tty=True):
        env = {**_INTERACTIVE_ENV, **(extra_env or {})}
        err = _TTY() if tty else io.StringIO()
        out = io.StringIO()
        with (
            mock.patch.dict(os.environ, env),
            mock.patch("sys.stdin.isatty", return_value=stdin_tty),
        ):
            with redirect_stderr(err):
                from contextlib import redirect_stdout

                with redirect_stdout(out):
                    code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_demo_shows_wordmark_on_tty(self) -> None:
        _, out, err = self._run_with_stderr(["demo"], tty=True)
        self.assertIn("Agent_Sudo", err)  # wordmark on stderr
        self.assertIn("AGENT_SUDO INTERACTIVE DEMO", out)  # demo body on stdout

    def test_demo_hides_wordmark_off_tty(self) -> None:
        _, out, err = self._run_with_stderr(["demo"], tty=False)
        self.assertNotIn("Agent_Sudo v", err)
        self.assertIn("AGENT_SUDO INTERACTIVE DEMO", out)

    def test_demo_hides_wordmark_in_ci_even_on_tty(self) -> None:
        _, _, err = self._run_with_stderr(["demo"], tty=True, extra_env={"CI": "1"})
        self.assertNotIn("Agent_Sudo v", err)

    def test_interactive_setup_shows_wordmark(self) -> None:
        with mock.patch("builtins.input", return_value="2"):
            _, out, err = self._run_with_stderr(["setup"], tty=True, stdin_tty=True)
        self.assertIn("Agent_Sudo", err)  # wordmark + menu on stderr
        self.assertIn("[mcp_servers.agent-sudo]", out)  # chosen config on stdout

    def test_explicit_setup_does_not_show_wordmark(self) -> None:
        # Naming a target is a scriptable path: no wordmark, even on a tty.
        _, out, err = self._run_with_stderr(["setup", "codex"], tty=True)
        self.assertNotIn("Agent_Sudo v", err)
        self.assertIn("[mcp_servers.agent-sudo]", out)


if __name__ == "__main__":
    unittest.main()
