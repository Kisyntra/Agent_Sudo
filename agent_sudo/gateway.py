from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

from agent_sudo import __version_label__
from agent_sudo.approvals import ApprovalProvider, init_approval_config
from agent_sudo.audit import AuditLogger, verify_audit_log
from agent_sudo.classifier import ActionClassifier
from agent_sudo.delegations import DelegationStore
from agent_sudo.doctor import doctor_exit_code, format_doctor_checks, run_doctor
from agent_sudo.models import ActionRequest, Decision, GatewayResult, OriginType, TrustLevel
from agent_sudo.policy import Policy, load_default_policy, load_policy


class PermissionGateway:
    def __init__(
        self,
        policy: Policy,
        approvals: ApprovalProvider | None = None,
        audit_logger: AuditLogger | None = None,
        delegation_store: DelegationStore | None = None,
    ):
        self.policy = policy
        self.classifier = ActionClassifier(policy)
        self.approvals = approvals or ApprovalProvider()
        self.audit_logger = audit_logger
        self.delegation_store = delegation_store

    def evaluate(self, request: ActionRequest, *, dry_run: bool = False) -> GatewayResult:
        classification = self.classifier.classify(request)
        policy_result = self.policy.decision_for(classification)
        decision = policy_result.decision
        approval_method = "none"
        reason = policy_result.reason
        approval_attempts: list[dict[str, object]] = []

        if dry_run and decision in {Decision.REQUIRE_APPROVAL, Decision.REQUIRE_STRONG_APPROVAL}:
            approval_method = "dry_run"
            reason = f"{reason}; approval skipped in dry-run"
        elif decision in {Decision.REQUIRE_APPROVAL, Decision.REQUIRE_STRONG_APPROVAL} and self.delegation_store:
            delegated, delegation_reason, delegation_method = self.delegation_store.authorize(
                request,
                classification=classification,
            )
            if delegated is True:
                decision = Decision.ALLOW
                approval_method = delegation_method
                reason = delegation_reason
                approval_attempts.append(
                    {
                        "approved": True,
                        "method": delegation_method,
                        "reason": delegation_reason,
                        "pending": False,
                    }
                )
            elif delegated is False:
                decision = Decision.DENY
                approval_method = delegation_method
                reason = delegation_reason
                approval_attempts.append(
                    {
                        "approved": False,
                        "method": delegation_method,
                        "reason": delegation_reason,
                        "pending": False,
                    }
                )
            else:
                decision, approval_method, reason, approval_attempts = self._prompt_for_approval(
                    request,
                    decision,
                    approval_attempts,
                )
        elif _external_content_requires_delegation(request, decision):
            approval_method = "DENY"
            decision = Decision.DENY
            reason = "external content cannot approve, escalate, or initiate tool execution without delegation"
            approval_attempts.append(
                {
                    "approved": False,
                    "method": "DENY",
                    "reason": reason,
                    "pending": False,
                }
            )
        elif decision in {Decision.REQUIRE_APPROVAL, Decision.REQUIRE_STRONG_APPROVAL}:
            decision, approval_method, reason, approval_attempts = self._prompt_for_approval(
                request,
                decision,
                approval_attempts,
            )

        result = GatewayResult(
            request=request,
            classification=classification,
            decision=decision,
            approval_method=approval_method,
            reason=reason,
            dry_run=dry_run,
            approval_attempts=approval_attempts,
        )
        if self.audit_logger is not None:
            self.audit_logger.record(result)
        return result

    def _prompt_for_approval(
        self,
        request: ActionRequest,
        decision: Decision,
        approval_attempts: list[dict[str, object]],
    ) -> tuple[Decision, str, str, list[dict[str, object]]]:
        if decision == Decision.REQUIRE_APPROVAL:
            approval = self.approvals.approve_sensitive(request)
            approval_method = approval.method
            approval_attempts.append(approval.to_dict())
            if approval.pending:
                decision = Decision.REQUIRE_APPROVAL
            else:
                decision = Decision.ALLOW if approval.approved else Decision.DENY
            reason = approval.reason
            return decision, approval_method, reason, approval_attempts
        if decision == Decision.REQUIRE_STRONG_APPROVAL:
            approval = self.approvals.approve_critical(request)
            approval_method = approval.method
            approval_attempts.append(approval.to_dict())
            if approval.pending:
                decision = Decision.REQUIRE_STRONG_APPROVAL
            else:
                decision = Decision.ALLOW if approval.approved else Decision.DENY
            reason = approval.reason
            return decision, approval_method, reason, approval_attempts
        return decision, "none", "approval not required", approval_attempts


def _external_content_requires_delegation(request: ActionRequest, decision: Decision) -> bool:
    if decision not in {Decision.REQUIRE_APPROVAL, Decision.REQUIRE_STRONG_APPROVAL}:
        return False
    return request.source_trust == TrustLevel.EXTERNAL_CONTENT or request.provenance.origin_type == OriginType.EXTERNAL_CONTENT


def load_requests(path: Path) -> list[ActionRequest]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw if isinstance(raw, list) else [raw]
    if not isinstance(items, list):
        raise ValueError("request file must contain a JSON object or list")
    return [ActionRequest.from_dict(item) for item in items]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-sudo")
    parser.add_argument("--version", action="version", version=f"agent-sudo {__version_label__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser("check", help="Classify requests and show policy decisions")
    check_parser.add_argument("request_file", type=Path)
    check_parser.add_argument("--policy", type=Path, help="Path to policy YAML")

    run_parser = subparsers.add_parser("run", help="Evaluate requests with approvals and audit logging")
    run_parser.add_argument("request_file", type=Path)
    run_parser.add_argument("--policy", type=Path, help="Path to policy YAML")
    run_parser.add_argument("--dry-run", action="store_true", help="Skip approval prompts")
    run_parser.add_argument(
        "--audit-log",
        type=Path,
        default=Path(".agent-sudo/audit.jsonl"),
        help="Audit JSONL path",
    )

    hermes_parser = subparsers.add_parser("hermes-check", help="Normalize and check an agent native tool call")
    hermes_parser.add_argument("tool_call_file", type=Path)
    hermes_parser.add_argument("--policy", type=Path, help="Path to policy YAML")

    codex_parser = subparsers.add_parser("codex-check", help="Normalize and check a Codex native tool call")
    codex_parser.add_argument("tool_call_file", type=Path)
    codex_parser.add_argument("--policy", type=Path, help="Path to policy YAML")

    generic_check_parser = subparsers.add_parser("generic-check", help="Normalize and check a universal tool call")
    generic_check_parser.add_argument("tool_call_file", type=Path)
    generic_check_parser.add_argument("--policy", type=Path, help="Path to policy YAML")

    generic_run_parser = subparsers.add_parser("generic-run", help="Evaluate a universal tool call")
    generic_run_parser.add_argument("tool_call_file", type=Path)
    generic_run_parser.add_argument("--policy", type=Path, help="Path to policy YAML")
    generic_run_parser.add_argument("--dry-run", action="store_true")
    generic_run_parser.add_argument("--audit-log", type=Path, default=Path(".agent-sudo/audit.jsonl"))

    verify_parser = subparsers.add_parser("verify-audit", help="Verify audit JSONL hash chain")
    verify_parser.add_argument("audit_log", type=Path)

    subparsers.add_parser("init-approval", help="Initialize local approval passphrase hash")
    subparsers.add_parser("doctor", help="Check local agent-sudo readiness")

    setup_parser = subparsers.add_parser("setup", help="Print dry-run setup checklist for an agent runtime")
    setup_parser.add_argument("agent", choices=["hermes", "codex", "claude-desktop", "openclaw"])

    delegate_parser = subparsers.add_parser("delegate", help="Manage scoped delegation tokens")
    delegate_subparsers = delegate_parser.add_subparsers(dest="delegate_command", required=True)

    delegate_create = delegate_subparsers.add_parser("create", help="Create a scoped delegation token")
    delegate_create.add_argument("--actor", required=True)
    delegate_create.add_argument("--allow-action", action="append", required=True, dest="allowed_actions")
    delegate_create.add_argument("--allow-path", action="append", required=True, dest="allowed_paths")
    delegate_create.add_argument("--deny-action", action="append", default=[], dest="denied_actions")
    delegate_create.add_argument("--ttl-seconds", type=int, default=7200)
    delegate_create.add_argument("--max-uses", type=int, default=1)
    delegate_create.add_argument("--reason", default="")
    delegate_create.add_argument("--critical", action="store_true")
    delegate_create.add_argument("--delegations-file", type=Path)

    delegate_list = delegate_subparsers.add_parser("list", help="List delegation tokens")
    delegate_list.add_argument("--delegations-file", type=Path)

    delegate_revoke = delegate_subparsers.add_parser("revoke", help="Revoke a delegation token")
    delegate_revoke.add_argument("token_id")
    delegate_revoke.add_argument("--delegations-file", type=Path)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command == "verify-audit":
        ok, message = verify_audit_log(args.audit_log)
        print(message)
        return 0 if ok else 1
    if args.command == "init-approval":
        try:
            init_approval_config()
        except ValueError as exc:
            print(f"init-approval failed: {exc}", file=sys.stderr)
            return 1
        print("approval config initialized")
        return 0
    if args.command == "doctor":
        checks = run_doctor()
        print(format_doctor_checks(checks))
        return doctor_exit_code(checks)
    if args.command == "setup":
        from agent_sudo.setup_guides import setup_lines

        print(f"agent-sudo setup checklist for {args.agent}")
        print("dry-run only: no config files were edited")
        for index, line in enumerate(setup_lines(args.agent), start=1):
            print(f"{index}. {line}")
        return 0
    if args.command == "delegate":
        store = DelegationStore(args.delegations_file) if args.delegations_file else DelegationStore()
        if args.delegate_command == "create":
            token = store.create(
                actor=args.actor,
                allowed_actions=args.allowed_actions,
                allowed_paths=args.allowed_paths,
                denied_actions=args.denied_actions,
                ttl_seconds=args.ttl_seconds,
                max_uses=args.max_uses,
                reason=args.reason,
                critical=args.critical,
            )
            print(json.dumps(token.to_dict(), sort_keys=True))
            return 0
        if args.delegate_command == "list":
            print(json.dumps([token.to_dict() for token in store.list()], indent=2, sort_keys=True))
            return 0
        if args.delegate_command == "revoke":
            token = store.revoke(args.token_id)
            if token is None:
                print(f"delegation token not found: {args.token_id}", file=sys.stderr)
                return 1
            print(json.dumps(token.to_dict(), sort_keys=True))
            return 0

    policy = load_policy(args.policy) if args.policy else load_default_policy()
    if args.command == "hermes-check":
        from agent_sudo.adapters.hermes import from_hermes_tool_call

        request = from_hermes_tool_call(load_tool_call(args.tool_call_file))
        result = PermissionGateway(policy).evaluate(request, dry_run=True)
        _print_result(result)
        return 0

    if args.command == "codex-check":
        from agent_sudo.adapters.codex import from_codex_tool_call

        request = from_codex_tool_call(load_tool_call(args.tool_call_file))
        result = PermissionGateway(policy).evaluate(request, dry_run=True)
        _print_result(result)
        return 0

    if args.command == "generic-check":
        from agent_sudo.adapters.generic import from_generic_tool_call

        request = from_generic_tool_call(load_tool_call(args.tool_call_file))
        result = PermissionGateway(policy).evaluate(request, dry_run=True)
        _print_result(result)
        return 0

    if args.command == "generic-run":
        from agent_sudo.adapters.generic import from_generic_tool_call
        from agent_sudo.executors import SafeToolExecutor, ShellCommandExecutor

        request = from_generic_tool_call(load_tool_call(args.tool_call_file))
        audit_logger = None if args.dry_run else AuditLogger(args.audit_log)
        gateway = PermissionGateway(policy, audit_logger=audit_logger)
        executor = SafeToolExecutor(gateway, ShellCommandExecutor())
        execution = executor.dry_run(request) if args.dry_run else executor.execute(request)
        _print_execution_result(execution)
        return 0 if args.dry_run or execution.gateway_result.decision != Decision.DENY else 2

    requests = load_requests(args.request_file)

    if args.command == "check":
        gateway = PermissionGateway(policy)
        for result in (gateway.evaluate(request, dry_run=True) for request in requests):
            _print_result(result)
        return _exit_code_for(results=None)

    audit_logger = None if args.dry_run else AuditLogger(args.audit_log)
    gateway = PermissionGateway(policy, audit_logger=audit_logger)
    results = [gateway.evaluate(request, dry_run=args.dry_run) for request in requests]
    for result in results:
        _print_result(result)
    return _exit_code_for(results, dry_run=args.dry_run)


def _print_result(result: GatewayResult) -> None:
    print(
        json.dumps(
            {
                "actor": result.request.actor,
                "action": result.request.action,
                "target": result.request.target,
                "classification": result.classification.value,
                "decision": result.decision.value,
                "approval_method": result.approval_method,
                "approval_attempts": result.approval_attempts,
                "reason": result.reason,
                "dry_run": result.dry_run,
            },
            sort_keys=True,
        )
    )


def _print_execution_result(result: object) -> None:
    print(
        json.dumps(
            {
                "action": result.request.action,
                "actor": result.request.actor,
                "target": result.request.target,
                "classification": result.gateway_result.classification.value,
                "decision": result.gateway_result.decision.value,
                "executed": result.executed,
                "exit_code": result.exit_code,
                "reason": result.reason,
                "dry_run": result.gateway_result.dry_run,
            },
            sort_keys=True,
        )
    )


def load_tool_call(path: Path) -> dict[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("tool call file must contain a JSON object")
    return raw


def _exit_code_for(results: list[GatewayResult] | None, *, dry_run: bool = False) -> int:
    if not results:
        return 0
    if dry_run:
        return 0
    return 2 if any(result.decision == Decision.DENY for result in results) else 0


if __name__ == "__main__":
    sys.exit(main())
