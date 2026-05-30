# Implementation Roadmap: agent-sudo Approval UI

This document details the multi-phase implementation roadmap for the `agent-sudo` secure approval UI, specifying milestones, code impacts, protocols, and migration boundaries.

---

## Phase 1: Minimal Notification MVP

### Goal
Provide desktop alerts when pending approvals are created without running a persistent background service or socket listener, relying instead on standard OS shell integration.

### Execution Flow
1. `PermissionGateway.evaluate()` encounters a request requiring approval.
2. It writes the `PENDING` request to `pending_approvals.json`.
3. It spawns a short-lived subprocess to trigger a native notification:
   * **macOS**: `osascript -e 'display notification "Approval requested for..." with title "agent-sudo"'`
   * **Linux**: `notify-send "agent-sudo" "Approval requested for..."`
   * **Windows**: Powershell notification helper.
4. Clicking the notification launches a popup input window (using Python's built-in `tkinter` module) displaying the target context (actor, action, target).
   * For `SENSITIVE` classifications: Offers **Approve** or **Deny** buttons.
   * For `CRITICAL` classifications: Shows a password text input to verify the approval passphrase.
5. Tkinter updates `pending_approvals.json` to `APPROVED` or `DENIED` and exits.

### Estimated Codebase Impact
* **Files Modified**:
  * `agent_sudo/gateway.py`: ~40 LOC added (to trigger the notification process in `_create_pending_approval`).
  * `agent_sudo/approvals.py`: ~80 LOC added (lightweight Tkinter dialog provider).
* **New Files**:
  * `tests/test_ui_mvp.py`: ~80 LOC (mocking subprocess/Tkinter interfaces).
* **Estimated LOC**: ~200 lines of Python.

### Security Impact
* **Isolation**: All prompts run within the user's active login session.
* **No Open Ports**: No loopback HTTP servers or background daemons are introduced, preserving the existing surface area.
* **Passphrase Verification**: Handled locally via `verify_passphrase` against PBKDF2 parameters.

---

## Phase 2: Daemon Architecture & IPC Protocol

### Goal
Decouple GUI rendering from the main execution thread by establishing a background daemon and standard socket IPC.

### Component Design
* **The Daemon (`agent-sudo-daemon`)**:
  * Runs as a user space agent (via `launchd` on macOS, `systemd --user` on Linux).
  * Listens on a UNIX domain socket at `~/.agent-sudo/ipc.sock`.
* **The Client**:
  * `PermissionGateway` attempts to open a socket connection to `ipc.sock`.
  * If successful, it writes the request metadata and exits immediately without waiting for UI interaction.
  * If the socket is unreachable, it logs a trace and falls back to Phase 1/CLI command output.

### IPC Protocol
The protocol utilizes JSON-RPC 2.0 over Unix domain sockets:

#### Request (Gateway to Daemon)
```json
{
  "jsonrpc": "2.0",
  "method": "request_approval",
  "params": {
    "approval_request_id": "848202b8-bfab-430c-843e-c045b8ad28f0",
    "actor": "mcp-client",
    "action": "run_shell_command",
    "target": "npm install",
    "classification": "CRITICAL",
    "reason": "Shell execution is critical by default"
  },
  "id": 1
}
```

#### Response (Daemon to Gateway)
```json
{
  "jsonrpc": "2.0",
  "result": {
    "status": "pending_created"
  },
  "id": 1
}
```

### Approval Lifecycle States
```text
[Gateway]                         [ipc.sock]                      [Daemon]
   │                                  │                               │
   ├── 1. Write PENDING to disk ─────>│                               │
   ├── 2. Send JSON-RPC notify ──────>│                               │
   │                                  ├── 3. Forward message ────────>│
   │                                  │                               ├── 4. Spawn UI Popup
   │                                  │                               ├── 5. Verify input
   │                                  │                               ├── 6. Write APPROVED/DENIED
   │                                  │                               └── 7. Log to audit.jsonl
```

---

## Phase 3: Touch ID & Keychain Integration

### Goal
Replace text passphrase confirmations on macOS with secure hardware-backed biometric verification.

### Mechanism
1. **LocalAuthentication Integration**:
   * The UI popup invokes macOS native LocalAuthentication API context:
     ```swift
     import LocalAuthentication
     let context = LAContext()
     context.evaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, localizedReason: "Approve critical tool call") { success, error in ... }
     ```
   * Access is queried via `PyObjC` bindings or a pre-compiled helper binary included in the package.
2. **Keychain Protection**:
   * On `init-approval`, `agent-sudo` generates a unique local symmetric key stored in the macOS Keychain.
   * This key is used by the daemon to cryptographically sign the `APPROVED` result inside `pending_approvals.json`.
   * The gateway verifies the signature before authorizing execution, preventing arbitrary file writes to `pending_approvals.json` from bypassing approval checks.

---

## Migration, Rollback, & Compatibility

### Compatibility with Terminal Approvals
* **Single Source of Truth**: The files `pending_approvals.json` and `audit.jsonl` remain the shared state records.
* **Interoperability**: A pending request can be approved via the GUI popup or by running `agent-sudo approve <id>` in the terminal. Both flows read and update the same state fields.

### Migration Path
1. **Opt-in Service**: The daemon and UI components are packaged in an optional dependency block:
   ```bash
   pip install agent-sudo-mcp[ui]
   ```
2. **Doctor Verification**: `agent-sudo doctor` checks for the active socket daemon and daemon health checks:
   ```text
   OK: approval daemon active - ipc.sock listening
   ```

### Rollback Strategy
* **Fail Safe Fallback**: If the daemon crashes, the Unix socket goes down, or the GUI helper fails to launch, the gateway automatically falls back to printing the standard command:
  ```text
  pending approval created: <id>; run `agent-sudo approve <id>`
  ```
  without interrupting the core agent execution boundaries.
* **Simple Disabling**: The daemon can be uninstalled or stopped without changing policy files or deleting passphrases:
  ```bash
  agent-sudo daemon stop
  ```
