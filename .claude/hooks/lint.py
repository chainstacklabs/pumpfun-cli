#!/usr/bin/env python3
"""Post-edit lint hook: ruff format + check on changed Python files."""

import json
import os
import subprocess
import sys

data = json.load(sys.stdin)
file_path = data.get("tool_input", {}).get("file_path", "")

# Only lint Python files
if not file_path.endswith(".py"):
    sys.exit(0)

# Only lint files inside our project
proj = os.environ.get("CLAUDE_PROJECT_DIR", "")
if proj and not file_path.startswith(proj):
    sys.exit(0)

exit_code = 0

# Format the single file (uses project's [tool.ruff] config via uv run)
subprocess.run(
    ["uv", "run", "ruff", "format", file_path],
    capture_output=True,
    cwd=proj or None,
)

# Check the single file with auto-fix
result = subprocess.run(
    ["uv", "run", "ruff", "check", "--fix", file_path],
    capture_output=True,
    text=True,
    cwd=proj or None,
)

if result.returncode != 0:
    output = result.stdout + result.stderr
    if output.strip():
        print(output, end="", file=sys.stderr)
    exit_code = 2

sys.exit(exit_code)
