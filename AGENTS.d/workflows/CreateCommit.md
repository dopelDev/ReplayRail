# Workflow Annex — CreateCommit

This file is an annex referenced by [`AGENTS.md`](../../AGENTS.md) and inherits its Global Rules and confirmation requirements.

Related:

- [`GenerateProjectReport`](GenerateProjectReport.md)

---

## Goal

Create a single, high-quality Git commit using a **consistent, readable, and structured commit message format**.

---

## Invocation

Run only when explicitly requested and confirmed.

Example requests:

- "Run the CreateCommit workflow"
- "Commit the current changes"
- "Use CreateCommit to create a commit"

---

## Steps

1. **Review changes**
   - `git status`
   - `git diff --name-status`
   - `git diff`
   - `git log -1 --pretty=medium`

2. **Stage intended changes**
   - Default: `git add .`
   - If unexpected files appear, stop and ask what to include

3. **Create commit**
   - Draft the commit message using the **canonical format** below
   - The commit message MUST be written to a temporary file under `/tmp` to preserve multiline formatting.
   - Example:
     - `tmp_msg="$(mktemp /tmp/codex-commit-message.XXXXXX.md)"`
     - `cat > "$tmp_msg" <<'EOF'`
     - `[paste here the canonical multiline commit message]`
     - `EOF`
     - `git commit -F "$tmp_msg"`
   - Create exactly one commit:
     - `git commit -F "$tmp_msg"` (using the file written in the step above)

---

## Canonical Commit Message Format (MANDATORY)

All commits created by this workflow MUST follow this format exactly.

```
<Commit Title>

Summary:

- bullet

- bullet

File changes:

- file/path: short description

- file/path: short description

Implications:

- Security: none | low | medium | high

- Ops: none | low | medium | high

- Compatibility: none | low | medium | high

- User-facing: none | low | medium | high

Verification:

- how this was verified, or "Not run (reason)"

Follow-ups:

- optional, or "None"

```

## Formatting Rules

- The title must be imperative and specific
- Use real line breaks (no escaped "\n")
- Section headers MUST be present even if values are "None"
- Bullets MUST be hyphen-prefixed (`-`)
- The message MUST be readable in `git log` without extra flags

---

## Commit Safety Rules

- Exactly ONE commit per execution
- Do NOT rewrite history:
  - no `--amend`
  - no `rebase`
  - no `reset`
  - no `cherry-pick`
- Do NOT restage repeatedly
- If the working tree changes after staging, stop and ask
