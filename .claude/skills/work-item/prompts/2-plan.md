# Stage 2: Plan Implementation for Work Item #{{ITEM_NUMBER}}

You are designing the implementation plan for a work item in the pumpfun-cli project. You have the investigation output from Stage 1. Your job is to produce a concrete, step-by-step plan that another agent will follow to implement the feature using TDD.

## Work Item

{{ITEM_DESCRIPTION}}

## Investigation Output

{{INVESTIGATION_OUTPUT}}

## Project Conventions (from CLAUDE.md)

- **Architecture:** `commands/` (thin Typer CLI) → `core/` (business logic) → `protocol/` (Solana). Never bypass layers.
- **Output:** Use `render(data, json_mode)` for success, `error(msg, hint, exit_code)` for failures. Never use `print()`.
- **Errors:** Core functions return `dict` with `"error"` key for expected failures. `error()` raises `SystemExit`.
- **Async:** All I/O is `async def`. Commands bridge with `asyncio.run()`. Close `RpcClient` in `finally`.
- **Types:** Full type hints on all public function signatures.
- **Imports:** stdlib → third-party → local.
- **Adding a command:** 1) `core/feature.py` 2) `commands/feature.py` 3) Register in `cli.py` 4) Tests in `tests/test_core/`

## Your Task

1. **Design the implementation bottom-up:** protocol → core → commands. Each layer should have clear inputs/outputs.
2. **Define test cases first** (TDD). For each test, specify:
   - Test function name
   - What it asserts
   - Which tier it belongs to (unit/surfpool/mainnet)
   - Which test file it goes in
3. **Order the work:** Write tests first, then implement layer by layer.
4. **Identify new dependencies or config changes** if any.
5. **Carry forward the test tiers** from the investigation.

## Output Format

Structure your response EXACTLY as follows:

## Implementation Steps
<Ordered list. For each step:>
1. **File:** `exact/path/to/file.py` (create | modify)
   **Change:** <what to add/modify — be specific about function signatures, parameters, return types>

## Test Plan
<For each test:>
- `test_function_name` in `tests/path/test_file.py` [unit|surfpool|mainnet]
  Asserts: <what the test checks>
  Setup: <what mocking/fixtures are needed>

## Test Tiers
<Carried from investigation. State which tiers the implementation stage should cover.>

## API Surface
<New CLI flags, commands, or output fields. Include exact flag names, types, defaults.>

## Error Handling
<For each expected failure mode:>
- **Condition:** <when it happens>
- **Response:** <what the core function returns / what error() emits>
- **User sees:** <the error message and hint>

## CONSTRAINTS

- DO NOT write code. You are planning only.
- DO NOT edit any files. You are read-only.
- Be specific about file paths, function names, and parameter types — the implementing agent needs exact targets.
