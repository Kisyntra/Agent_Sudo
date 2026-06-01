"""Asserts the PydanticAI dogfood example enforces as intended.

Skipped when pydantic-ai is not installed (the dependency-free core suite under
`python -m unittest discover`), so it never breaks default CI. Runs when the
examples extra is present:  pip install -e ".[examples]"
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

# Runner-agnostic skip guard (works under both unittest and pytest, and does
# not require pytest to be installed). The example imports pydantic_ai at top.
try:
    from examples.pydantic_ai.example import run_demo

    HAS_PYDANTIC_AI = True
    _IMPORT_ERROR = ""
except ImportError as exc:  # pragma: no cover - exercised only without the extra
    HAS_PYDANTIC_AI = False
    _IMPORT_ERROR = str(exc)


@unittest.skipUnless(HAS_PYDANTIC_AI, f"pydantic-ai not installed: {_IMPORT_ERROR}")
class PydanticAIDogfoodTests(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self._dir.name)
        self.r = run_demo(self.tmp)

    def tearDown(self) -> None:
        self._dir.cleanup()

    def test_safe_read_returns_real_file_content(self) -> None:
        self.assertEqual(self.r["safe_read"]["tool_output"], "hello from disk")

    def test_undelegated_write_is_held_not_allowed(self) -> None:
        held = self.r["write_held"]
        self.assertFalse(held["file_written"])  # REQUIRE_APPROVAL != ALLOW
        self.assertIn("REQUIRE_APPROVAL", held["tool_output"])

    def test_delegated_write_executes_via_delegation(self) -> None:
        deleg = self.r["write_delegated"]
        self.assertTrue(deleg["file_written"])
        self.assertIn("DELEGATION", deleg["tool_output"])

    def test_blocked_action_is_denied_and_not_executed(self) -> None:
        blocked = self.r["blocked"]
        self.assertFalse(blocked["exfiltrated"])
        self.assertIn("DENY", blocked["tool_output"])

    def test_audit_chain_verifies(self) -> None:
        self.assertTrue(self.r["audit"]["verified"])
        self.assertEqual(self.r["audit"]["records"], 4)

    def test_no_state_written_outside_tempdir(self) -> None:
        # Everything the demo wrote must live under the temp dir.
        self.assertTrue((self.tmp / "audit.jsonl").exists())
        self.assertTrue((self.tmp / "delegations.json").exists())


if __name__ == "__main__":
    unittest.main()
