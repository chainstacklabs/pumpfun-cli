#!/usr/bin/env python3
"""Pre-edit guard: block writes to sensitive files."""

import json
import os
import sys

data = json.load(sys.stdin)
file_path = data.get("tool_input", {}).get("file_path", "")
proj = os.environ.get("CLAUDE_PROJECT_DIR", "")

# --- Protected patterns ---
BLOCKED_EXACT = {".env", ".env.local", ".env.production"}
BLOCKED_DIRS = {"idl/"}
BLOCKED_SUFFIXES = (".pem", ".key", ".secret")
BLOCKED_NAMES = {"wallet.enc"}

rel = os.path.relpath(file_path, proj) if proj else file_path
name = os.path.basename(rel)

if rel in BLOCKED_EXACT:
    print(f"BLOCKED: {rel} is a secrets file — edit manually", file=sys.stderr)
    sys.exit(2)

for d in BLOCKED_DIRS:
    if rel.startswith(d):
        print(
            f"BLOCKED: {rel} is in {d} (source-of-truth from on-chain) — don't edit",
            file=sys.stderr,
        )
        sys.exit(2)

if rel.endswith(BLOCKED_SUFFIXES):
    print(f"BLOCKED: {rel} looks like a credential file", file=sys.stderr)
    sys.exit(2)

if name in BLOCKED_NAMES:
    print(f"BLOCKED: {name} is the encrypted wallet keystore — don't edit", file=sys.stderr)
    sys.exit(2)
