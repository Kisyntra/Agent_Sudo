# Release Notes: Agent_Sudo v0.5.1

Patch release. Makes the file-backed delegation and audit stores safe under
parallel tool execution. No format changes, no new dependencies, no public API
changes.

## Security / Correctness

- **Concurrency-safe one-use delegation consumption (#38).** The delegation
  consume path (`DelegationStore.authorize(consume=True)`, plus `create` and
  `revoke`) now performs its entire read → check → increment → write under an
  exclusive POSIX advisory lock (`fcntl.flock`) and re-reads token state from
  disk inside the lock. This closes a race in which concurrent consumers could
  each observe `uses=0` and all be allowed, double-spending a `max_uses=1`
  token. `save()` now publishes atomically (temp file → `fsync` → `os.replace`
  → directory `fsync`) so a reader or crash never sees a partial delegations
  file.
- **Concurrency-safe audit append (#38).** `AuditLogger._write_entry` now holds
  the same exclusive lock across read-last-hash → link → append → `fsync`, so
  concurrent appends can no longer read the same `previous_hash` and fork the
  SHA-256 hash chain. The chain stays linear and `verify-audit`-clean under
  parallel writes.
- **Fail-closed under lock contention and corruption (#38).** If the lock
  cannot be acquired within the timeout, or the store is unreadable/corrupt, or
  the audit log has a torn tail, the gateway denies (delegation) or raises
  (audit) rather than falling open or silently continuing. No broad `except`
  masking is introduced; existing fail-closed behavior is preserved.

## Compatibility

- **No format changes.** `delegations.json` and `audit.jsonl` are byte-for-byte
  identical to v0.5.0. The only new on-disk artifacts are sibling `*.lock` files
  used purely for lock state.
- **No new dependencies.** Standard library only (`fcntl`). Public signatures
  are unchanged — `lock_timeout` is a keyword-only argument with a default on
  `DelegationStore` and `AuditLogger`.

## Known Limitations

- Locking is POSIX-only (macOS/Linux), matching the supported runtimes. There is
  no Windows code path.
