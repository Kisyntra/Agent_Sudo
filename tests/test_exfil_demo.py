"""Smoke test for the flagship exfiltration-prevention demo.

Locks the three scenario decisions so the demo can never silently lie if the
classifier or policy changes, and confirms the generated audit log verifies.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_sudo.audit import verify_audit_log

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_PATH = REPO_ROOT / "examples" / "exfil_demo" / "demo.py"


def _load_demo_module():
    spec = importlib.util.spec_from_file_location("exfil_demo_demo", DEMO_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


demo = _load_demo_module()


class ExfilDemoSmokeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.audit_path = Path(self._tmp.name) / "audit.jsonl"
        self.gateway = demo.build_gateway(self.audit_path)
        self.results = demo.evaluate_all(self.gateway)
        self.by_key = {scenario["key"]: result for scenario, result in self.results}

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_scenario_1_user_read_is_allowed(self) -> None:
        self.assertEqual(self.by_key["user_read"].decision.name, "ALLOW")

    def test_scenario_2_injected_exfiltration_is_denied(self) -> None:
        self.assertEqual(self.by_key["injected_exfil"].decision.name, "DENY")

    def test_scenario_3_external_origin_requires_approval(self) -> None:
        self.assertEqual(self.by_key["external_read"].decision.name, "REQUIRE_APPROVAL")

    def test_each_scenario_matches_its_pinned_expectation(self) -> None:
        for scenario, result in self.results:
            self.assertEqual(
                result.decision.name,
                scenario["expected"],
                msg=f"{scenario['key']} expected {scenario['expected']}, got {result.decision.name}",
            )

    def test_provenance_is_the_only_difference_between_1_and_3(self) -> None:
        # Same tool/action/target; only the origin differs -> different verdict.
        r1 = next(s["request"] for s, _ in self.results if s["key"] == "user_read")
        r3 = next(s["request"] for s, _ in self.results if s["key"] == "external_read")
        self.assertEqual(
            (r1.tool, r1.action, r1.target), (r3.tool, r3.action, r3.target)
        )
        self.assertNotEqual(
            r1.provenance.origin_type,
            r3.provenance.origin_type,
        )
        self.assertNotEqual(
            self.by_key["user_read"].decision.name,
            self.by_key["external_read"].decision.name,
        )

    def test_audit_log_has_three_entries_and_verifies(self) -> None:
        lines = [
            ln
            for ln in self.audit_path.read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]
        self.assertEqual(len(lines), 3)
        ok, message = verify_audit_log(self.audit_path)
        self.assertTrue(ok, msg=message)


if __name__ == "__main__":
    unittest.main()
