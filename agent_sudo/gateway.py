from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

from agent_sudo import __version_label__
from agent_sudo.approvals import ApprovalProvider, init_approval_config, CONFIG_PATH
from agent_sudo.audit import AuditLogger, verify_audit_log
from agent_sudo.classifier import ActionClassifier
from agent_sudo.delegations import DelegationStore, DELEGATIONS_PATH
from agent_sudo.doctor import doctor_exit_code, format_doctor_checks, run_doctor
from agent_sudo.models import ActionRequest, ApprovalStatus, Classification, Decision, GatewayResult, OriginType, TrustLevel
from agent_sudo.pending_approvals import (
    PENDING_APPROVALS_PATH,
    PendingApprovalStore,
    approval_command,
    format_pending_approvals,
    resolve_approval_identifier,
    expires_in_seconds,
)
from agent_sudo.policy import Policy, load_default_policy, load_policy


class PermissionGateway:
    def __init__(
        self,
        policy: Policy,
        approvals: ApprovalProvider | None = None,
        audit_logger: AuditLogger | None = None,
        delegation_store: DelegationStore | None = None,
        pending_approval_store: PendingApprovalStore | None = None,
    ):
        self.policy = policy
        self.classifier = ActionClassifier(policy)
        self.approvals = approvals or ApprovalProvider()
        self.audit_logger = audit_logger
        self.delegation_store = delegation_store
        self.pending_approval_store = pending_approval_store

    def evaluate(self, request: ActionRequest, *, dry_run: bool = False) -> GatewayResult:
        classification = self.classifier.classify(request)
        policy_result = self.policy.decision_for(classification)
        decision = policy_result.decision
        approval_method = "none"
        reason = policy_result.reason
        approval_attempts: list[dict[str, object]] = []
        approval_request_id = ""
        approval_command_text = ""
        approval_expires_at = ""
        approval_expires_in_seconds: int | None = None

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
                pending_decision = self._evaluate_pending_approval(request)
                if pending_decision is not None:
                    (
                        decision,
                        approval_method,
                        reason,
                        approval_request_id,
                        approval_command_text,
                        approval_expires_at,
                        approval_expires_in_seconds,
                    ) = pending_decision
                else:
                    (
                        decision,
                        approval_method,
                        reason,
                        approval_attempts,
                        approval_request_id,
                        approval_command_text,
                        approval_expires_at,
                        approval_expires_in_seconds,
                    ) = self._prompt_for_approval(
                        request,
                        classification,
                        decision,
                        approval_attempts,
                    )
                if delegation_method == "DELEGATION":
                    reason = f"{delegation_reason}; {reason}"
        elif decision in {Decision.REQUIRE_APPROVAL, Decision.REQUIRE_STRONG_APPROVAL} and self.pending_approval_store:
            pending_decision = self._evaluate_pending_approval(request)
            if pending_decision is not None:
                (
                    decision,
                    approval_method,
                    reason,
                    approval_request_id,
                    approval_command_text,
                    approval_expires_at,
                    approval_expires_in_seconds,
                ) = pending_decision
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
            else:
                (
                    decision,
                    approval_method,
                    reason,
                    approval_attempts,
                    approval_request_id,
                    approval_command_text,
                    approval_expires_at,
                    approval_expires_in_seconds,
                ) = self._prompt_for_approval(
                    request,
                    classification,
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
            (
                decision,
                approval_method,
                reason,
                approval_attempts,
                approval_request_id,
                approval_command_text,
                approval_expires_at,
                approval_expires_in_seconds,
            ) = self._prompt_for_approval(
                request,
                classification,
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
            approval_request_id=approval_request_id,
            approval_command=approval_command_text,
            approval_expires_at=approval_expires_at,
            approval_expires_in_seconds=approval_expires_in_seconds,
        )
        if self.audit_logger is not None:
            self.audit_logger.record(result)
        return result

    def _prompt_for_approval(
        self,
        request: ActionRequest,
        classification: Classification,
        decision: Decision,
        approval_attempts: list[dict[str, object]],
    ) -> tuple[Decision, str, str, list[dict[str, object]], str, str, str, int | None]:
        if decision == Decision.REQUIRE_APPROVAL:
            approval = self.approvals.approve_sensitive(request)
            approval_method = approval.method
            approval_attempts.append(approval.to_dict())
            if approval.pending:
                approval_id, command, reason, expires_at, expires_in = self._create_pending_approval(
                    request,
                    classification,
                    decision,
                    approval_method,
                    approval.reason,
                )
                decision = Decision.REQUIRE_APPROVAL
                return decision, approval_method, reason, approval_attempts, approval_id, command, expires_at, expires_in
            else:
                decision = Decision.ALLOW if approval.approved else Decision.DENY
            reason = approval.reason
            return decision, approval_method, reason, approval_attempts, "", "", "", None
        if decision == Decision.REQUIRE_STRONG_APPROVAL:
            approval = self.approvals.approve_critical(request)
            approval_method = approval.method
            approval_attempts.append(approval.to_dict())
            if approval.pending:
                approval_id, command, reason, expires_at, expires_in = self._create_pending_approval(
                    request,
                    classification,
                    decision,
                    approval_method,
                    approval.reason,
                )
                decision = Decision.REQUIRE_STRONG_APPROVAL
                return decision, approval_method, reason, approval_attempts, approval_id, command, expires_at, expires_in
            else:
                decision = Decision.ALLOW if approval.approved else Decision.DENY
            reason = approval.reason
            return decision, approval_method, reason, approval_attempts, "", "", "", None
        return decision, "none", "approval not required", approval_attempts, "", "", "", None

    def _evaluate_pending_approval(
        self,
        request: ActionRequest,
    ) -> tuple[Decision, str, str, str, str, str, int | None] | None:
        if self.pending_approval_store is None:
            return None
        approval = self.pending_approval_store.find_matching(request)
        if approval is None:
            return None
        if approval.status == ApprovalStatus.APPROVED:
            used = self.pending_approval_store.consume_matching(request)
            if used is not None:
                return (
                    Decision.ALLOW,
                    "PENDING_APPROVAL",
                    f"approved by pending approval {used.approval_request_id}",
                    used.approval_request_id,
                    "",
                    "",
                    None,
                )
        command = approval_command(approval.approval_request_id)
        if approval.status == ApprovalStatus.PENDING:
            return (
                approval.decision,
                approval.required_approval_method,
                approval.reason,
                approval.approval_request_id,
                command,
                approval.expires_at,
                expires_in_seconds(approval),
            )
        return (
            Decision.DENY,
            "PENDING_APPROVAL",
            f"approval request is {approval.status.value}",
            approval.approval_request_id,
            "",
            "",
            None,
        )

    def _create_pending_approval(
        self,
        request: ActionRequest,
        classification: Classification,
        decision: Decision,
        required_approval_method: str,
        reason: str,
    ) -> tuple[str, str, str, str, int | None]:
        config_path = self.approvals.config_path if hasattr(self.approvals, "config_path") else CONFIG_PATH
        if not config_path.exists():
            sys.stderr.write(
                "approval system not initialized\n\n"
                "Run:\n"
                "agent-sudo init-approval\n\n"
                "to create a local approval passphrase.\n"
            )
        if self.pending_approval_store is None:
            return "", "", reason, "", None
        approval = self.pending_approval_store.create(
            action_request=request,
            classification=classification,
            decision=decision,
            required_approval_method=required_approval_method,
            reason=reason,
        )
        command = approval_command(approval.approval_request_id)
        return (
            approval.approval_request_id,
            command,
            f"{reason}; pending approval created: {approval.approval_request_id}; run `{command}`",
            approval.expires_at,
            expires_in_seconds(approval),
        )


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
    run_parser.add_argument("--notify", action="store_true", help="Enable desktop notifications for pending approvals")
    run_parser.add_argument("--open-approval-terminal", action="store_true", help="Automatically open Terminal.app for pending approvals")

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
    generic_run_parser.add_argument("--notify", action="store_true", help="Enable desktop notifications for pending approvals")
    generic_run_parser.add_argument("--open-approval-terminal", action="store_true", help="Automatically open Terminal.app for pending approvals")

    verify_parser = subparsers.add_parser("verify-audit", help="Verify audit JSONL hash chain")
    verify_parser.add_argument("audit_log", type=Path)

    init_parser = subparsers.add_parser(
        "init-approval",
        help="Initialize or reset local approval passphrase hash",
        description=(
            "Initialize or reset the local agent-sudo passphrase hash. "
            "If a passphrase already exists, resetting it will: "
            "(1) revoke all existing delegation tokens, "
            "(2) cancel all active pending or approved requests, "
            "(3) preserve existing audit logs, and "
            "(4) log a chained 'passphrase_reset' event to the audit log. "
            "The old passphrase is one-way hashed only and cannot be recovered."
        ),
    )
    init_parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    init_parser.add_argument("--pending-approvals-file", type=Path, default=PENDING_APPROVALS_PATH)
    init_parser.add_argument("--delegations-file", type=Path, default=DELEGATIONS_PATH)
    init_parser.add_argument("--audit-log", type=Path, default=Path(".agent-sudo/audit.jsonl"))
    init_parser.add_argument("--force", action="store_true")
    subparsers.add_parser("doctor", help="Check local agent-sudo readiness")

    approvals_parser = subparsers.add_parser("approvals", help="Manage pending approval requests")
    approvals_subparsers = approvals_parser.add_subparsers(dest="approvals_command", required=True)
    approvals_list = approvals_subparsers.add_parser("list", help="List pending approval requests")
    approvals_list.add_argument("--pending-approvals-file", type=Path, default=PENDING_APPROVALS_PATH)

    pending_parser = subparsers.add_parser("pending", help="List active pending approval requests")
    pending_parser.add_argument("--pending-approvals-file", type=Path, default=PENDING_APPROVALS_PATH)

    approve_parser = subparsers.add_parser("approve", help="Approve a pending approval request")
    approve_parser.add_argument("approval_request_id")
    approve_parser.add_argument("--pending-approvals-file", type=Path, default=PENDING_APPROVALS_PATH)
    approve_parser.add_argument("--audit-log", type=Path)
    approve_parser.add_argument("--approval-config", type=Path)

    deny_parser = subparsers.add_parser("deny", help="Deny a pending approval request")
    deny_parser.add_argument("approval_request_id")
    deny_parser.add_argument("--pending-approvals-file", type=Path, default=PENDING_APPROVALS_PATH)
    deny_parser.add_argument("--audit-log", type=Path)

    helper_parser = subparsers.add_parser("approval-helper", help="Guided terminal approval helper for pending requests")
    helper_parser.add_argument("--pending-approvals-file", type=Path, default=PENDING_APPROVALS_PATH)
    helper_parser.add_argument("--approval-config", type=Path, default=CONFIG_PATH)
    helper_parser.add_argument("--audit-log", type=Path)
    helper_parser.add_argument("--watch", action="store_true", help="Continuously poll and watch for new requests")
    helper_parser.add_argument("--auto-opened", action="store_true", help="Minimal display mode with auto-close logic for auto-opened terminals")

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

    upgrade_parser = subparsers.add_parser("upgrade-local", help="Safe local upgrade of agent-sudo")
    upgrade_parser.add_argument("--check", action="store_true", help="Check for available upgrades without updating")
    upgrade_parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Allow upgrading even with user changes; generated artifacts are cleaned automatically without this flag",
    )

    context_parser = subparsers.add_parser("context", help="Detect and return the runtime workspace context as JSON")
    context_parser.add_argument("--workspace", help="Path to configured workspace root")

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
            init_approval_config(
                config_path=args.config,
                pending_approvals_path=args.pending_approvals_file,
                delegations_path=args.delegations_file,
                audit_log_path=args.audit_log,
                force=args.force,
            )
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
    if args.command == "approvals":
        store = PendingApprovalStore(args.pending_approvals_file)
        if args.approvals_command == "list":
            print(json.dumps([approval.to_dict() for approval in store.list()], indent=2, sort_keys=True))
            return 0
    if args.command == "pending":
        store = PendingApprovalStore(args.pending_approvals_file)
        print(format_pending_approvals(store.list()))
        return 0
    if args.command == "approve":
        config_path = args.approval_config or CONFIG_PATH
        if not config_path.exists():
            sys.stderr.write(
                "approval system not initialized\n\n"
                "Run:\n"
                "agent-sudo init-approval\n\n"
                "to create a local approval passphrase.\n"
            )
            return 1
        audit_logger = AuditLogger(args.audit_log) if args.audit_log else None
        store = PendingApprovalStore(args.pending_approvals_file, audit_logger=audit_logger)
        approval_id = resolve_approval_identifier(args.approval_request_id, store.list())
        if approval_id is None:
            print(f"approval request not found: {args.approval_request_id}", file=sys.stderr)
            return 1
        provider_kwargs = {"config_path": config_path}
        approval, result = store.approve(
            approval_id,
            approval_provider=ApprovalProvider(**provider_kwargs),
        )
        if approval is None:
            print(result.reason, file=sys.stderr)
            return 1
        if not result.approved:
            print(f"Error: {result.reason}", file=sys.stderr)
            return 1
        print(json.dumps(approval.to_dict(), sort_keys=True))
        return 0
    if args.command == "deny":
        audit_logger = AuditLogger(args.audit_log) if args.audit_log else None
        store = PendingApprovalStore(args.pending_approvals_file, audit_logger=audit_logger)
        approval = store.deny(args.approval_request_id)
        if approval is None:
            print(f"approval request not found: {args.approval_request_id}", file=sys.stderr)
            return 1
        print(json.dumps(approval.to_dict(), sort_keys=True))
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

    if args.command == "upgrade-local":
        from agent_sudo.upgrade import handle_upgrade
        return handle_upgrade(check_only=args.check, allow_dirty=args.allow_dirty)

    if args.command == "context":
        from agent_sudo.context import detect_runtime_context
        ctx = detect_runtime_context(workspace=args.workspace)
        print(json.dumps(ctx.to_dict(), indent=2, sort_keys=True))
        return 0

    if args.command == "approval-helper":
        from agent_sudo.helper import run_approval_helper
        return run_approval_helper(
            pending_approvals_path=args.pending_approvals_file,
            config_path=args.approval_config,
            audit_log_path=args.audit_log,
            watch=args.watch,
            auto_opened=args.auto_opened,
        )

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
        pending_store = None if args.dry_run else PendingApprovalStore(
            notify=getattr(args, "notify", False),
            open_approval_terminal=getattr(args, "open_approval_terminal", None)
        )
        gateway = PermissionGateway(policy, audit_logger=audit_logger, pending_approval_store=pending_store)
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
    pending_store = None if args.dry_run else PendingApprovalStore(
        notify=getattr(args, "notify", False),
        open_approval_terminal=getattr(args, "open_approval_terminal", None)
    )
    gateway = PermissionGateway(policy, audit_logger=audit_logger, pending_approval_store=pending_store)
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
