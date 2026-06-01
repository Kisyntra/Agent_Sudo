#!/usr/bin/env bash
#
# Driver for recording the exfil demo without VHS (asciinema or any screen
# capture). It echoes each command, runs it, and pauses so a viewer can read.
#
# asciinema path:
#   asciinema rec --overwrite -c "bash examples/exfil_demo/recording/record.sh" exfil-demo.cast
#   agg exfil-demo.cast exfil-demo.gif          # asciinema/agg -> GIF
#
# Screen-capture path: start your recorder, then run:
#   bash examples/exfil_demo/recording/record.sh
#
# Total runtime ~16s of pauses + output; trim to <60s in post if needed.

set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

show() { printf '\n\033[1m$ %s\033[0m\n' "$1"; }

# 1) The poisoned page the agent fetched (note the hidden SYSTEM OVERRIDE)
show "cat examples/exfil_demo/poisoned_page.txt"
cat examples/exfil_demo/poisoned_page.txt
sleep 4

# 2) Run the demo — three provenance-based verdicts
show "python examples/exfil_demo/demo.py"
python examples/exfil_demo/demo.py
sleep 7

# 3) Verify the audit log's hash chain (tamper-evident)
show "agent-sudo verify-audit examples/exfil_demo/audit.jsonl"
agent-sudo verify-audit examples/exfil_demo/audit.jsonl
sleep 3
