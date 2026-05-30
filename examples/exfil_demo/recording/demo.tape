# VHS tape for the Agent_Sudo exfiltration-prevention demo GIF.
#
# Render (run from the repo root):
#   vhs examples/exfil_demo/recording/demo.tape
# Produces: exfil-demo.gif  (~25s runtime, well under the 60s budget)
#
# VHS: https://github.com/charmbracelet/vhs   (brew install vhs)

Output exfil-demo.gif

Require python3
Require agent-sudo

Set Shell "bash"
Set FontSize 18
Set Width 1280
Set Height 760
Set Theme "Dracula"
Set TypingSpeed 45ms
Set Padding 24

# 1) Show the poisoned page the agent "fetched" — note the hidden SYSTEM OVERRIDE.
Type "# 1) The web page the agent fetched — note the hidden SYSTEM OVERRIDE:"
Enter
Sleep 700ms
Type "cat examples/exfil_demo/poisoned_page.txt"
Enter
Sleep 4500ms

Type "clear"
Enter
Sleep 300ms

# 2) Run the demo — three provenance-based verdicts: ALLOW / DENY / REQUIRE_APPROVAL.
Type "# 2) Run the demo — watch the three provenance-based verdicts:"
Enter
Sleep 600ms
Type "python examples/exfil_demo/demo.py"
Enter
Sleep 7000ms

# 3) Prove the audit log's hash chain is intact (tamper-evident).
Type "# 3) Verify the audit log's hash chain (tamper-evident):"
Enter
Sleep 600ms
Type "agent-sudo verify-audit examples/exfil_demo/audit.jsonl"
Enter
Sleep 3000ms

Sleep 2000ms
