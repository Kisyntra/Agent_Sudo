"""Token-first delegation lifecycle trace for the audit log.

`agent-sudo audit trace <token_id>` reconstructs what an audit log records about
a single delegation token: the token's grant metadata (from the delegation
store), every audit entry that *references* the token, the observed consumes and
denials, and the causes the denial reasons *cite*.

Read-only. No schema, no models, no provenance, and no approval-lifecycle
reconstruction. Faithful to the claims contract: store-state and log-observed
quantities are reported separately and labelled by source; the tool never claims
an exact usage count from the log, an intended token, or definitive causality.
A delegation reason enumerates *every* token evaluated for an action, so a
reference does not mean the agent meant this token.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_sudo.audit import (
    _entry_request,
    _parse_audit_timestamp,
    read_audit_entries,
)
from agent_sudo.delegations import default_delegations_path

# Reason grammar (the contract from delegations.py):
#   consume:  "delegated by <token_id>: <token reason>"
#   mismatch: "delegation token <token_id> mismatched: <cause, cause, ...>"
# tokens are joined by "; "; causes within one token's segment by ", ".
_CONSUME_PREFIX = "delegated by "
_MISMATCH_PREFIX = "delegation token "
_MISMATCH_INFIX = " mismatched:"

# (substring to look for in a reason segment, canonical cause label)
_CAUSE_KEYWORDS = [
    ("token exhausted", "token exhausted"),
    ("token expired", "token expired"),
    ("token revoked", "token revoked"),
    ("action mismatch", "action mismatch"),
    ("path mismatch", "path mismatch"),
    ("denied action", "denied action"),
    ("actor mismatch", "actor mismatch"),
    ("critical flag missing", "critical flag missing"),
]

_MAX_SAMPLE_ROWS = 6


def _consume_tokens(reason: str) -> set[str]:
    """Token ids that this reason records as successfully consumed."""
    tokens: set[str] = set()
    for segment in reason.split("; "):
        idx = segment.find(_CONSUME_PREFIX)
        if idx == -1:
            continue
        rest = segment[idx + len(_CONSUME_PREFIX) :]
        token = rest.split(":", 1)[0].strip()
        if token:
            tokens.add(token)
    return tokens


def _mismatch_tokens(reason: str) -> set[str]:
    """Token ids that this reason records as mismatched (denied)."""
    tokens: set[str] = set()
    for segment in reason.split("; "):
        if _MISMATCH_INFIX not in segment:
            continue
        idx = segment.find(_MISMATCH_PREFIX)
        if idx == -1:
            continue
        rest = segment[idx + len(_MISMATCH_PREFIX) :]
        token = rest.split(_MISMATCH_INFIX, 1)[0].strip()
        if token:
            tokens.add(token)
    return tokens


def _delegation_chain(entry: dict[str, Any]) -> list[str]:
    provenance = _entry_request(entry).get("provenance")
    if isinstance(provenance, dict):
        chain = provenance.get("delegation_chain")
        if isinstance(chain, list):
            return [str(item) for item in chain]
    return []


def _token_segment(reason: str, token_id: str) -> str:
    """The reason segment naming this token's mismatch, isolated from others.

    Critical for faithfulness: a multi-token reason lists each token's causes,
    so causes must be attributed only to *this* token's segment.
    """
    needle = f"{_MISMATCH_PREFIX}{token_id}{_MISMATCH_INFIX}"
    for segment in reason.split("; "):
        if needle in segment:
            return segment
    return ""


def _causes_in(segment: str) -> list[str]:
    return [label for needle, label in _CAUSE_KEYWORDS if needle in segment]


def all_token_ids(
    entries: list[dict[str, Any]], delegations: list[dict[str, Any]]
) -> set[str]:
    ids = {str(d.get("token_id")) for d in delegations if d.get("token_id")}
    for entry in entries:
        reason = str(entry.get("reason", ""))
        ids |= _consume_tokens(reason) | _mismatch_tokens(reason)
        ids |= set(_delegation_chain(entry))
    return ids


def resolve_token(
    token_input: str,
    entries: list[dict[str, Any]],
    delegations: list[dict[str, Any]],
) -> tuple[str | None, list[str]]:
    """Resolve an exact id or a unique prefix.

    Returns ``(token_id, [])`` on a unique match, or ``(None, candidates)`` when
    nothing matches (empty list) or a prefix is ambiguous (>1 candidate).
    """
    ids = all_token_ids(entries, delegations)
    if token_input in ids:
        return token_input, []
    matches = sorted(t for t in ids if t.startswith(token_input))
    if len(matches) == 1:
        return matches[0], []
    return None, matches


def status_of(metadata: dict[str, Any] | None) -> tuple[str, str]:
    """Store-derived status. Never inferred from the log scan."""
    if metadata is None:
        return "UNKNOWN", "no store record (token not in delegations.json)"
    if metadata.get("revoked"):
        return "REVOKED", "store: revoked=true"
    uses = int(metadata.get("uses", 0))
    max_uses = int(metadata.get("max_uses", 0))
    if max_uses and uses >= max_uses:
        return "EXHAUSTED", f"store: uses {uses} == max {max_uses}"
    expires = _parse_audit_timestamp(str(metadata.get("expires_at", "")))
    if expires is not None and expires < datetime.now(timezone.utc):
        return "EXPIRED", f"store: past expires_at {metadata.get('expires_at')}"
    return "ACTIVE", f"store: uses {uses}/{max_uses}, not revoked, within expiry"


def build_trace(
    token_id: str,
    entries: list[dict[str, Any]],
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    references: list[dict[str, Any]] = []
    consumes = 0
    denials = 0
    cause_counts: dict[str, int] = {}
    raw_sample: list[Any] | None = None

    for index, entry in enumerate(entries, start=1):
        reason = str(entry.get("reason", ""))
        in_consume = token_id in _consume_tokens(reason)
        in_mismatch = token_id in _mismatch_tokens(reason)
        in_chain = token_id in _delegation_chain(entry)
        if not (in_consume or in_mismatch or in_chain):
            continue

        decision = str(entry.get("decision", ""))
        request = _entry_request(entry)
        is_consume = in_consume or (in_chain and decision == "ALLOW")
        kind = "consume" if is_consume else "denial"

        if kind == "consume":
            consumes += 1
        else:
            denials += 1
            segment = _token_segment(reason, token_id)
            for cause in _causes_in(segment):
                cause_counts[cause] = cause_counts.get(cause, 0) + 1
            if raw_sample is None and segment:
                raw_sample = [index, segment]

        references.append(
            {
                "index": index,
                "timestamp": str(entry.get("timestamp", "")),
                "decision": decision,
                "action": str(request.get("action", "")),
                "target": str(request.get("target", "")),
                "kind": kind,
                "reason": reason,
            }
        )

    status, status_basis = status_of(metadata)
    actor = ""
    if metadata is not None:
        actor = str(metadata.get("actor", ""))
    if not actor and references:
        actor = str(
            _entry_request(entries[references[0]["index"] - 1]).get("actor", "")
        )

    return {
        "token_id": token_id,
        "actor": actor,
        "status": status,
        "status_basis": status_basis,
        "metadata": metadata,
        "counts": {
            "references": len(references),
            "observed_consumes": consumes,
            "observed_denials": denials,
        },
        "inferred_causes": cause_counts,
        "raw_sample": raw_sample,
        "references": references,
    }


def _clip(value: str, width: int) -> str:
    return value if len(value) <= width else value[: max(0, width - 1)] + "…"


def format_trace(trace: dict[str, Any]) -> str:
    meta = trace["metadata"]
    counts = trace["counts"]
    lines: list[str] = []
    actor = trace["actor"] or "—"
    lines.append(f"Delegation  {trace['token_id']}        actor: {actor}")

    if meta is not None:
        label = str(meta.get("reason", "")) or "—"
        actions = meta.get("allowed_actions", [])
        paths = meta.get("allowed_paths", [])
        lines.append(f"  label    {label}")
        lines.append(f"  scope    action ∈ {actions}   path ∈ {paths}")
        lines.append(
            "  store    "
            f"max_uses={meta.get('max_uses')}  uses={meta.get('uses')}  "
            f"created {meta.get('created_at')}  expires {meta.get('expires_at')}  "
            f"revoked={str(bool(meta.get('revoked'))).lower()}"
        )
    else:
        lines.append(
            "  scope    (no store record — token not found in delegations.json)"
        )

    lines.append(f"  status   {trace['status']} ({trace['status_basis']})")
    lines.append("")
    lines.append(
        "  observed in log:  "
        f"{counts['references']} audit references  ·  "
        f"{counts['observed_consumes']} observed consumes  ·  "
        f"{counts['observed_denials']} observed denials"
    )

    shown = trace["references"][:_MAX_SAMPLE_ROWS]
    for ref in shown:
        time = str(ref["timestamp"])[:19]
        if ref["kind"] == "consume":
            note = "delegated by this token"
        else:
            seg = _token_segment(str(ref["reason"]), trace["token_id"])
            causes = _causes_in(seg)
            note = "reason cites: " + (
                " · ".join(causes) if causes else "(uncategorized)"
            )
        lines.append(
            f"    #{ref['index']:<4} {time}  {ref['decision']:<22} "
            f"{_clip(ref['action'], 18):<18} {_clip(ref['target'], 24):<24} {note}"
        )
    remaining = counts["references"] - len(shown)
    if remaining > 0:
        lines.append(f"    … ({remaining} more references)")

    if trace["inferred_causes"]:
        lines.append("")
        lines.append(
            "  inferred causes (across "
            f"{counts['observed_denials']} observed denials; "
            "causes co-occur; counts are reference counts, not attempts)"
        )
        for cause, n in sorted(
            trace["inferred_causes"].items(), key=lambda kv: (-kv[1], kv[0])
        ):
            lines.append(f"    reason cites {cause} … {n}")

    if trace["raw_sample"]:
        idx, segment = trace["raw_sample"]
        lines.append("")
        lines.append("  raw (verbatim reason segment — A3 fallback):")
        lines.append(f"    #{idx}  {segment}")

    return "\n".join(lines)


def _load_delegations(
    audit_log: Path, delegations_file: Path | None
) -> list[dict[str, Any]]:
    path = delegations_file
    if path is None:
        sibling = audit_log.parent / "delegations.json"
        path = sibling if sibling.exists() else default_delegations_path()
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return raw if isinstance(raw, list) else []


def _not_found_message(token_input: str, audit_log: Path, n_store: int) -> str:
    return (
        f"No delegation found for '{token_input}'.\n\n"
        f"Searched delegations.json ({n_store} tokens) and the audit log "
        "references — no token id matches.\n"
        "To find a token id, scan the reason of denied/allowed rows:\n"
        f"  agent-sudo audit list {audit_log} --non-allow --json\n"
        "  (the table clips long reasons; --json shows the full "
        "'delegated by <id>' / 'delegation token <id> mismatched: …')\n"
    )


def run_trace(
    token_input: str,
    audit_log: Path,
    delegations_file: Path | None,
    *,
    as_json: bool = False,
) -> int:
    entries = read_audit_entries(audit_log)
    delegations = _load_delegations(audit_log, delegations_file)
    token_id, candidates = resolve_token(token_input, entries, delegations)

    if token_id is None:
        if candidates:
            sys.stderr.write(
                f"ambiguous token prefix '{token_input}' matches "
                f"{len(candidates)} tokens:\n"
            )
            for candidate in candidates[:10]:
                sys.stderr.write(f"  {candidate}\n")
            if len(candidates) > 10:
                sys.stderr.write(f"  … and {len(candidates) - 10} more\n")
        else:
            sys.stderr.write(
                _not_found_message(token_input, audit_log, len(delegations))
            )
        return 1

    metadata = next(
        (d for d in delegations if str(d.get("token_id")) == token_id), None
    )
    trace = build_trace(token_id, entries, metadata)
    if as_json:
        print(json.dumps(trace, indent=2, sort_keys=True))
    else:
        print(format_trace(trace))
    return 0
