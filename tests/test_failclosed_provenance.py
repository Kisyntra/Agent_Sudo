"""Fail-closed provenance defaults.

When a request arrives without trustworthy provenance, Agent_Sudo must treat it
as UNKNOWN (untrusted) rather than USER_DIRECT. These tests pin that posture
across the MCP wire path, the dict/model path, and the dataclass default, and
document the one thing this change intentionally does NOT solve: a caller that
*forges* an explicit USER_DIRECT is still believed (see the final test).
"""

from __future__ import annotations

import unittest

from agent_sudo.adapters.mcp import from_mcp_tool_call
from agent_sudo.gateway import PermissionGateway
from agent_sudo.mcp_validation import tool_call_from_jsonrpc
from agent_sudo.models import ActionRequest, Classification, Decision, TrustLevel
from agent_sudo.policy import load_default_policy


def _safe_read(extra: dict | None = None) -> dict:
    """A JSON-RPC tools/call for a SAFE action, plus optional attestation."""
    message = {
        "jsonrpc": "2.0",
        "id": "t",
        "method": "tools/call",
        "params": {"name": "read_file", "arguments": {"path": "README.md"}},
    }
    if extra:
        message.update(extra)
    return message


class FailClosedProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gateway = PermissionGateway(load_default_policy())

    def test_missing_mcp_provenance_escalates_safe_action(self) -> None:
        # A JSON-RPC SAFE read that does not attest provenance must not run
        # silently: it fails closed to UNKNOWN trust and requires approval.
        tool_call = tool_call_from_jsonrpc(_safe_read())
        self.assertEqual(tool_call["source"], "unknown")
        self.assertEqual(tool_call["source_trust"], "UNKNOWN")

        request = from_mcp_tool_call(tool_call)
        result = self.gateway.evaluate(request, dry_run=True)
        self.assertEqual(result.classification, Classification.SENSITIVE)
        self.assertEqual(result.decision, Decision.REQUIRE_APPROVAL)

    def test_from_dict_missing_provenance_becomes_unknown(self) -> None:
        request = ActionRequest.from_dict(
            {
                "actor": "agent",
                "source": "unknown",
                "tool": "filesystem",
                "action": "read_file",
                "target": "README.md",
                "payload_summary": "read",
            }
        )
        self.assertEqual(request.source_trust, TrustLevel.UNKNOWN)

    def test_action_request_default_trust_is_unknown(self) -> None:
        request = ActionRequest(
            "agent", "unknown", "filesystem", "read_file", "README.md", "read"
        )
        self.assertEqual(request.source_trust, TrustLevel.UNKNOWN)

    def test_adapter_and_model_paths_align_on_unknown(self) -> None:
        # Same logical "SAFE read, no provenance" via the adapter path and the
        # model path must agree: both UNKNOWN, both escalate. Guards against the
        # two entry points drifting apart again.
        adapter_req = from_mcp_tool_call(
            {
                "actor": "agent",
                "tool": "read_file",
                "action": "read_file",
                "target": "README.md",
            }
        )
        model_req = ActionRequest.from_dict(
            {
                "actor": "agent",
                "source": "unknown",
                "tool": "filesystem",
                "action": "read_file",
                "target": "README.md",
                "payload_summary": "read",
            }
        )
        self.assertEqual(adapter_req.source_trust, TrustLevel.UNKNOWN)
        self.assertEqual(model_req.source_trust, TrustLevel.UNKNOWN)
        for req in (adapter_req, model_req):
            result = self.gateway.evaluate(req, dry_run=True)
            self.assertEqual(result.decision, Decision.REQUIRE_APPROVAL)

    def test_explicit_user_direct_is_preserved(self) -> None:
        # The change must not over-correct: an explicitly attested USER_DIRECT
        # SAFE action is still honored and allowed.
        request = ActionRequest.from_dict(
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
        self.assertEqual(request.source_trust, TrustLevel.USER_DIRECT)
        result = self.gateway.evaluate(request)
        self.assertEqual(result.decision, Decision.ALLOW)

        # And via the MCP wire path with attestation.
        attested = tool_call_from_jsonrpc(
            _safe_read({"source": "user", "source_trust": "USER_DIRECT"})
        )
        self.assertEqual(attested["source_trust"], "USER_DIRECT")

    def test_forged_user_direct_is_still_trusted_known_limitation(self) -> None:
        """KNOWN LIMITATION (intentionally not fixed in this PR).

        Provenance is self-attested. An adversarial agent can stamp every
        provenance field as USER_DIRECT even when the instruction actually
        originated from external content, and the gateway believes it —
        nothing yet binds trust elevation to a host-issued credential.

        (Note: a *partial* forgery is weaker — e.g. claiming USER_DIRECT trust
        while leaving source="webpage" still trips the origin_type escalation.
        The real bypass requires forging provenance consistently, below.)

        This test pins current behavior so a future host-attestation /
        nonce-binding change has a concrete assertion to flip. It is NOT an
        endorsement of the behavior. See docs/reports/provenance_trust_audit.md.
        """
        forged = from_mcp_tool_call(
            {
                "source": "user",  # the lie: external content claims to be the user
                "origin_type": "USER_DIRECT",
                "source_trust": "USER_DIRECT",
                "tool": "read_file",
                "action": "read_file",
                "target": "README.md",
            }
        )
        self.assertEqual(forged.source_trust, TrustLevel.USER_DIRECT)
        result = self.gateway.evaluate(forged)
        # Still ALLOW today — the consistent forgery succeeds. Documented here,
        # solved by a separate host-attestation effort, not this PR.
        self.assertEqual(result.decision, Decision.ALLOW)


if __name__ == "__main__":
    unittest.main()
