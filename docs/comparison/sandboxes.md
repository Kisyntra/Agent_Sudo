# Agent_Sudo vs. Container/VM Sandboxes (Docker, Firecracker)

This document details the architectural differences, security boundaries, and complementary relationships between application-level policy authorization (like `Agent_Sudo`) and environment-level process isolation sandboxes (like `Docker` and `Firecracker`).

---

## 1. Architectural Difference: Sandbox vs. Policy Engine

| Feature | Environment-Level Sandboxes (Docker, Firecracker) | Agent_Sudo Policy Engine |
| :--- | :--- | :--- |
| **Primary Question** | **"Where does code execute?"** | **"Should this action be allowed?"** |
| **Layer of Operation** | Operating System / Kernel boundary | Application logic / Intent boundary |
| **Isolation Boundary** | Virtualized CPU, Memory, Network, and Namespaces | YAML-based verification policy gates |
| **Visibility** | Opaque to application context (sees raw syscalls) | Aware of user intent, provenance, and schemas |
| **Approvals Flow** | Blocks at the OS level (raise permission errors) | Interactive yes/no prompts and passphrase confirmation |
| **Auditing Capability** | OS syslog or auditd log files (binary/low-level) | Cryptographically signed, hash-chained JSONL audit trail |

---

## 2. Docker vs. Agent_Sudo

### Docker Isolation
Docker uses Linux namespaces (mount, pid, net, ipc, uts, user) and control groups (cgroups) to restrict what processes can see and consume. 
*   **Security Focus**: Prevents the containerized agent from modifying the host system’s startup scripts, accessing host processes, or consuming host CPU/memory resources.
*   **The Limitation**: Within the mapped workspace directory (which is typically mounted into the container so the agent can write code or run commands), Docker offers **no protection**. An agent is free to delete files, overwrite configuration, exfiltrate credentials found in environmental variables, or run malicious code within the shared repository.

### Agent_Sudo Policy Gate
Agent_Sudo evaluates permission boundaries inside the workspace.
*   **Security Focus**: Detects the classification of individual actions. It blocks writes to startup files (e.g. `.bashrc`), exfiltration of secrets via network calls, or deletion of key configuration files, even if the directory is mounted with write permissions.
*   **The Complement**: If you run a developer agent, mount the repository inside a Docker container (to isolate the process), and use Agent_Sudo to gate the agent's file edits, command execution, and network tool accesses.

---

## 3. Firecracker vs. Agent_Sudo

### Firecracker microVMs
Firecracker runs lightweight virtual machines in user space using KVM. It achieves near-instant startup times with complete hardware-level virtualization.
*   **Security Focus**: Protects multi-tenant SaaS platforms where untrusted agent code runs on shared physical hardware.
*   **The Limitation**: Because Firecracker acts as a complete virtual machine, it runs headless and is entirely isolated from the user. It cannot easily prompt a local developer for approval, nor does it have awareness of user provenance (e.g. distinguishing whether a terminal command was requested directly by the human operator or triggered by an external webpage via prompt injection).

### Agent_Sudo Policy Gate
Agent_Sudo specializes in human-in-the-loop (HITL) workflows and provenance tracking.
*   **Security Focus**: It maps tool calls to a universal schema containing the request source (e.g. `user` vs. `webpage`). If an agent attempts to run a critical shell command, Agent_Sudo pauses the execution thread and prompts the developer locally or sends a notification to approve it.
*   **The Complement**: Multi-tenant SaaS platforms can run Firecracker VMs to isolate execution, and call Agent_Sudo's policy evaluation module to determine if a requested tool call is safe to run under the user's current delegation token constraints.

---

## 4. Practical Scenario Matrix

| Scenario | Raw Sandbox Alone (Docker/Firecracker) | Sandbox + Agent_Sudo Policy |
| :--- | :--- | :--- |
| **Malicious Network Exfiltration** | Allowed (Docker containers have outbound internet by default to fetch dependencies). | **Blocked** (Gateway flags network payload targets and denies low-trust source requests). |
| **Accidental `rm -rf /` or Workspace Deletion** | Executed normally (destroys files inside container/VM). | **Blocked** (Gated as a CRITICAL command; requires CLI validation/passphrase). |
| **API Keys Leakage from Environment** | Allowed (Agent reads environment variables inside container). | **Gated** (Protected read rules block access to credential paths and config folders). |
| **Malicious Code Injection in Mounts** | Allowed (Agent writes backdoor code directly to the mounted source path). | **Gated** (Gateway classifies executable file edits as sensitive, requiring confirmation). |

---

## 5. Security Recommendation

For robust local agent execution, combine isolation sandboxes with policy validation:
1.  **Isolation (Sandbox)**: Run the agent process inside Docker or a virtual machine to ensure that CPU, memory, and system resources are isolated.
2.  **Authorization (Agent_Sudo)**: Wrap the agent's tool interface with Agent_Sudo to enforce least-privilege policies, evaluate provenance risk, verify audit logs, and require human-in-the-loop approvals.
