"""Cross-field provenance consistency.

reconcile_trust() caps an explicitly-claimed `source_trust` at the floor its
`source`/`origin_type` evidence supports. A claim that exceeds the evidence is
downgraded (fail closed) and tagged with an `inconsistent_provenance` hint that
surfaces in the decision/audit reason. Internally consistent claims — including
a fully consistent forgery — are honored unchanged (the latter is a documented
limitation, see docs/reports/provenance_trust_audit.md).
"""

from __future__ import annotations

import unittest

from agent_sudo.adapters.mcp import from_mcp_tool_call
from agent_sudo.gateway import PermissionGateway
from agent_sudo.models import (
    INCONSISTENT_PROVENANCE_HINT,
    ActionRequest,
    Classification,
    Decision,
    TrustLevel,
)
from agent_sudo.policy import load_default_policy


def _has_inconsistency(request: ActionRequest) -> bool:
    return any(h.startswith(INCONSISTENT_PROVENANCE_HINT) for h in request.risk_hints)


class ProvenanceConsistencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gateway = PermissionGateway(load_default_policy())

    # 1. contradictory source / source_trust -> downgrade + approval
    def test_contradictory_source_trust_is_downgraded(self) -> None:
        request = from_mcp_tool_call(
            {
                "source": "webpage",
                "source_trust": "USER_DIRECT",  # contradicts external source
                "tool": "read_file",
                "action": "read_file",
                "target": "README.md",
            }
        )
        self.assertEqual(request.source_trust, TrustLevel.EXTERNAL_CONTENT)
        self.assertTrue(_has_inconsistency(request))

        result = self.gateway.evaluate(request, dry_run=True)
        self.assertEqual(result.classification, Classification.SENSITIVE)
        self.assertEqual(result.decision, Decision.REQUIRE_APPROVAL)
        self.assertIn(INCONSISTENT_PROVENANCE_HINT, result.reason)

    # 2. contradictory origin_type / source_trust -> downgrade + approval
    def test_contradictory_origin_type_is_downgraded(self) -> None:
        request = from_mcp_tool_call(
            {
                "source": "user",
                "origin_type": "EXTERNAL_CONTENT",  # contradicts USER_DIRECT trust
                "source_trust": "USER_DIRECT",
                "tool": "read_file",
                "action": "read_file",
                "target": "README.md",
            }
        )
        self.assertEqual(request.source_trust, TrustLevel.EXTERNAL_CONTENT)
        self.assertTrue(_has_inconsistency(request))
        result = self.gateway.evaluate(request, dry_run=True)
        self.assertEqual(result.decision, Decision.REQUIRE_APPROVAL)
        self.assertIn(INCONSISTENT_PROVENANCE_HINT, result.reason)

    # 3. model path (from_dict) behaves identically to the adapter path
    def test_model_path_parity(self) -> None:
        request = ActionRequest.from_dict(
            {
                "actor": "agent",
                "source": "webpage",
                "tool": "filesystem",
                "action": "read_file",
                "target": "README.md",
                "payload_summary": "read",
                "source_trust": "USER_DIRECT",
            }
        )
        self.assertEqual(request.source_trust, TrustLevel.EXTERNAL_CONTENT)
        self.assertTrue(_has_inconsistency(request))
        self.assertEqual(
            self.gateway.evaluate(request, dry_run=True).decision,
            Decision.REQUIRE_APPROVAL,
        )

    # 4. consistent USER_DIRECT still allows a SAFE action
    def test_consistent_user_direct_allows_safe_action(self) -> None:
        request = from_mcp_tool_call(
            {
                "source": "user",
                "origin_type": "USER_DIRECT",
                "source_trust": "USER_DIRECT",
                "tool": "read_file",
                "action": "read_file",
                "target": "README.md",
            }
        )
        self.assertEqual(request.source_trust, TrustLevel.USER_DIRECT)
        self.assertFalse(_has_inconsistency(request))
        self.assertEqual(self.gateway.evaluate(request).decision, Decision.ALLOW)

    # 5. self-restriction (claim lower than evidence) is honored, not flagged
    def test_self_restriction_is_not_a_contradiction(self) -> None:
        request = from_mcp_tool_call(
            {
                "source": "user",  # evidence would support USER_DIRECT
                "source_trust": "UNKNOWN",  # caller voluntarily claims less
                "tool": "read_file",
                "action": "read_file",
                "target": "README.md",
            }
        )
        self.assertEqual(request.source_trust, TrustLevel.UNKNOWN)
        self.assertFalse(_has_inconsistency(request))

    # 6. #28 invariants remain unchanged by this PR
    def test_hash_28_invariants_unchanged(self) -> None:
        # missing source_trust + no provenance => UNKNOWN, SAFE escalates
        missing = ActionRequest.from_dict(
            {
                "actor": "agent",
                "source": "unknown",
                "tool": "filesystem",
                "action": "read_file",
                "target": "README.md",
                "payload_summary": "read",
            }
        )
        self.assertEqual(missing.source_trust, TrustLevel.UNKNOWN)
        self.assertFalse(_has_inconsistency(missing))
        self.assertEqual(
            self.gateway.evaluate(missing, dry_run=True).decision,
            Decision.REQUIRE_APPROVAL,
        )
        # explicit consistent USER_DIRECT => ALLOW
        attested = ActionRequest.from_dict(
            {
                "actor": "agent",
                "source": "user",
                "tool": "filesystem",
                "action": "read_file",
                "target": "README.md",
                "payload_summary": "read",
                "source_trust": "USER_DIRECT",
            }
        )
        self.assertEqual(attested.source_trust, TrustLevel.USER_DIRECT)
        self.assertEqual(self.gateway.evaluate(attested).decision, Decision.ALLOW)

    # 7. consistent forgery is still believed -- documented known limitation
    def test_consistent_forged_user_direct_remains_known_limitation(self) -> None:
        """KNOWN LIMITATION (intentionally not solved here).

        A compromised agent that forges *every* provenance field consistently
        (source=user, origin_type=USER_DIRECT, source_trust=USER_DIRECT) leaves
        no internal contradiction for reconcile_trust() to catch, so the claim
        is honored. This is the irreducible gap that needs host attestation /
        nonce binding -- out of scope for cross-field consistency. Pinned so a
        future change has a concrete assertion to flip.
        """
        forged = from_mcp_tool_call(
            {
                "source": "user",
                "origin_type": "USER_DIRECT",
                "source_trust": "USER_DIRECT",
                "tool": "read_file",
                "action": "read_file",
                "target": "README.md",
            }
        )
        self.assertEqual(forged.source_trust, TrustLevel.USER_DIRECT)
        self.assertFalse(_has_inconsistency(forged))
        self.assertEqual(self.gateway.evaluate(forged).decision, Decision.ALLOW)


if __name__ == "__main__":
    unittest.main()
