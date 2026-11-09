#!/usr/bin/env python3
"""Pre-bash guard: block dangerous git operations, warn on transactions.

BLOCKS (exit 2): git add of docs/*.md (gitignored files).
ADVISORY (exit 0): transaction commands, mainnet tests, sensitive file deletion.
The note goes back as JSON `additionalContext`, the only channel Claude reads
on exit 0; the command still runs.
"""

import json
import re
import sys

data = json.load(sys.stdin)
command = data.get("tool_input", {}).get("command", "")

# Transaction-sending CLI commands
TX_COMMANDS = re.compile(
    r"\bpumpfun\b.*\b("
    r"buy|sell|transfer|launch|migrate|"
    r"close-atas|claim-cashback|close-volume-acc|collect-creator-fee"
    r")\b"
)

# Mainnet test scripts
MAINNET_PATTERNS = re.compile(r"mainnet[_-]test|mainnet\.sh")

# Deletion of sensitive files
SENSITIVE_DELETE = re.compile(
    r"\brm\b.*("
    r"\.env|wallet\.enc|\.pem|\.key|\.secret"
    r")"
)

# Deletion of IDL directory
IDL_DELETE = re.compile(r"\brm\b.*\bidl[/\s]")

# git add of docs/*.md files (gitignored — must never be staged)
GIT_ADD_DOCS_MD = re.compile(r"\bgit\s+add\b.*\bdocs/.*\.md\b")

if GIT_ADD_DOCS_MD.search(command):
    print(
        "BLOCKED: docs/*.md files are in .gitignore and must not be staged. "
        "Remove docs/ paths from your git add command.",
        file=sys.stderr,
    )
    sys.exit(2)

note = None
if TX_COMMANDS.search(command):
    note = "NOTE: This command sends a Solana transaction. On mainnet this costs real SOL."
elif MAINNET_PATTERNS.search(command):
    note = (
        "NOTE: This runs mainnet end-to-end tests (costs real SOL). "
        "Make sure the user has confirmed."
    )
elif SENSITIVE_DELETE.search(command):
    note = (
        "NOTE: This deletes a sensitive file (.env, wallet, or credentials). "
        "Make sure the user intended this."
    )
elif IDL_DELETE.search(command):
    note = (
        "NOTE: This deletes IDL files (source-of-truth from on-chain programs). "
        "These cannot be regenerated without fetching from chain."
    )

if note:
    print(
        json.dumps(
            {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": note}}
        )
    )

# Advisory only — never block
sys.exit(0)
