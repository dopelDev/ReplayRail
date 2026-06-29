# Workflow Annex — GenerateProjectReport

This file is an annex referenced by [`AGENTS.md`](../../AGENTS.md) and inherits its Global Rules and confirmation requirements.

Related:

- [`CreateCommit`](CreateCommit.md)

---

## Goal

Generate a reusable, human-readable **Project Report** that summarizes the repository progressively (by parts), suitable as context for future agents and for a human reviewer. The workflow must detect whether a new report is needed by comparing the current repo fingerprint against the latest report.

---

## Scope & Write Restrictions (MANDATORY)

This workflow may and should **read the entire repository** to build an accurate report.

It may only perform file writes that meet ALL of the following:

- Location: under `docs/reports/` only (create the folder if missing)
- Type: documentation only (prefer Markdown: `*.md`)
- Operations allowed: create new files or modify existing files
- Operations forbidden: delete files; modify any file outside `docs/reports/`

If the agent cannot comply with these write restrictions in the execution environment, it MUST stop and ask for guidance instead of writing elsewhere.

---

## Invocation (required)

Run only when explicitly requested **and** confirmed.

Example requests:

- "Run the GenerateProjectReport workflow"
- "Generate a project report for context"
- "Update the project report"

## Confirmation rule (mandatory)

Before executing, the agent MUST:

1. Restate: "GenerateProjectReport"
2. State side effects: reads repo, creates/updates files under `docs/reports/`
3. Ask for confirmation and wait for a clear "Proceed/Approved/Yes"

---

## Report Storage

- Reports root: `docs/reports/`
- Latest pointer: `docs/reports/LATEST.md`
- Index: `docs/reports/INDEX.md`
- Versioned report: `docs/reports/<YYYY-MM-DD>/<HH-MM-SS>.md`
- Analysis logs (optional deep dives): `docs/reports/logs/<YYYY-MM-DD>/<HH-MM-SS>--<area-slug>.md`

---

## Step 1: Locate the latest report (if any)

1. If `docs/reports/LATEST.md` exists, treat it as the latest report pointer.
2. Otherwise, find the most recent versioned report under `docs/reports/<YYYY-MM-DD>/<HH-MM-SS>.md` by timestamp (ignore `docs/reports/logs/`).
3. If no report exists, continue to Step 2 and generate the first one.

---

## Step 2: Compute the current Repo Fingerprint

### Purpose

decide whether a new report is needed.

Run:

- `git rev-parse HEAD` (if repo is Git; otherwise `HEAD: N/A`)
- `git status --porcelain=v1` (if Git; otherwise `STATUS: N/A`)
- Fingerprint (tracked content; MUST exclude reports to prevent regeneration loops):
  - `git ls-files -z -- . ':!docs/reports/**' | xargs -0 sha1sum | sha1sum`
  - If negative pathspecs are unsupported, use an equivalent filter that preserves NUL delimiters and excludes `docs/reports/`.

Interpretation rules:

- If `git status --porcelain=v1` is non-empty, mark **Working tree: dirty**
- If Git is unavailable, use a fallback fingerprint:
  - `find . -maxdepth 4 -type f ! -path "./.git/*" ! -path "./docs/reports/*" -print | sort | sha1sum`

---

## Step 3: Extract the previous fingerprint (if a report exists)

From the latest report (if present), read the `Repo Fingerprint` section and extract:

- HEAD
- Working tree state
- Fingerprint hash

If the latest report does not contain a fingerprint, treat it as **unknown** and generate a new report.

---

## Step 4: Mandatory Logical Decomposition

The agent MUST decompose the project into **logical areas**.

Rules:

- Areas MUST come from:
  - Project Summary
  - Repository structure
- Each area MUST be analyzed independently
- The agent MUST NOT produce a final summary yet

---

## Step 5: Mandatory Area Analysis Passes (NON-OPTIONAL)

For EACH logical area, perform an **analysis pass**.

Each pass MUST include:

- Purpose: why this area exists
- Responsibilities: what it owns
- Key files: entry points only
- Design choices: why it is structured this way
- Constraints: assumptions or limits
- Trade-offs: what was favored over alternatives

⚠️ The workflow MUST NOT proceed until ALL areas have been analyzed.

---

## Step 6: Synthesis (After All Areas)

Only after all area passes are complete, the agent may:

- Write a global Summary
- Identify cross-cutting concerns
- Derive risks and implications

---

### 6.A Diagrams (MANDATORY)

#### Logical Diagram

- Purpose: describe how logical areas interact
- Rules:
  - Focus on responsibilities and data/control flow
  - Avoid file-level detail
- Format:
  - Mermaid preferred
  - ASCII fallback allowed

#### Structural Diagram

- Purpose: describe repository structure
- Rules:
  - Reflect directories and major files
  - Group by responsibility, not depth

---

### 6.B Functional File Inventory (MANDATORY)

- List all relevant files grouped by functional responsibility
- Each group MUST explain why the files belong together

---

### 6.C Analysis Recommendations (MANDATORY)

- Propose 2–5 areas for deeper analysis
- Each recommendation MUST include:
  - Area name
  - Reason
  - Risk or unknown

---

### 6.D Deep-Dive Confirmation (MANDATORY)

Ask explicitly:

> "Do you want to run a deep analysis on any of these areas?"

Allowed answers:

- Yes + area(s)
- No
- Defer

---

### 6.E Iterative Area Deep Analysis (OPTIONAL)

- Re-run the Area Analysis Pass for confirmed areas only
- No global summary rewrite
- No fingerprint recomputation

---

### 6.F Fingerprint-Scoped Analysis Log (MANDATORY)

If deep analysis occurs:

- Write the Analysis Log entry to a new file (one file per entry); do not edit the existing Project Report
- Location: `docs/reports/logs/<YYYY-MM-DD>/<HH-MM-SS>--<area-slug>.md` (create directories as needed)
- The log MUST reference the same repo fingerprint as the triggering report
- Do NOT create a new Project Report
- The log MUST comply with Scope & Write Restrictions above

#### Analysis Log File Format

```
## Analysis Log — <YYYY-MM-DD HH:MM:SS>

Repo Fingerprint:
- <fingerprint from triggering report>
- Base report: <path to the Project Report this log is tied to>

Analyzed Area:
- <Area name>

Scope:
- Why this area was selected
- What was analyzed in this pass

Findings:
- Key observations specific to this area
- Important design decisions or patterns

Implications:
- Security: none | low | medium | high — <short justification>
- Ops: none | low | medium | high — <short justification>
- Compatibility: none | low | medium | high — <short justification>
- User-facing: none | low | medium | high — <short justification>

Notes:
- Constraints, open questions, or follow-up ideas

```

#### Rules

- Each Analysis Log lives in its own file; never append to or reorder existing logs
- Preserve existing log files; timestamps convey order
- Existing Project Report content MUST NOT be modified
- The analysis log MUST reference the same repo fingerprint as the triggering report
- No new fingerprint computation is allowed during this step

---

## Step 7: Canonical Report Format (MANDATORY)

All Project Reports generated by this workflow MUST follow this format exactly.
The report is designed to be reusable as context for future agents and humans.

```
<Project Report Title>

Summary:

- High-level description of the project purpose
- What this report covers and why it exists

Repo Fingerprint:

- HEAD: <commit hash or N/A>
- Working tree: clean | dirty | N/A
- Fingerprint: <hash>
- Generated at: <YYYY-MM-DD HH:MM:SS TZ>

Project Map:

- <Area / Module 1>: brief description of its role in the project
- <Area / Module 2>: brief description of its role in the project
- <Area / Module 3>: brief description of its role in the project

Key Components:

- <Component 1>: responsibilities, entry points, important files
- <Component 2>: responsibilities, entry points, important files
- <Component 3>: responsibilities, entry points, important files

Operational Notes:

- How the project is built, run, or deployed (only what is observed)
- Relevant commands, configs, or runtime assumptions

Risks / Implications:

- Security: none | low | medium | high — <short justification>
- Ops: none | low | medium | high — <short justification>
- Compatibility: none | low | medium | high — <short justification>
- User-facing: none | low | medium | high — <short justification>

Verification:

- What was verified (commands run, files checked)
- What was NOT verified and why

Follow-ups:

- Open questions
- Gaps in understanding
- Suggested next steps
- Or: None
```

---

### Formatting Rules

- Use real line breaks (no escaped "\n")
- Keep ALL section headers present (use "None" if empty)
- Use hyphen-prefixed bullets (`-`)
- Avoid speculation; explicitly label unknowns
- The report must be readable as-is when pasted into another agent session

---

## Step 8: Publish the Report (Versioning and Pointers)

1. Write the versioned report to:
   - `docs/reports/<YYYY-MM-DD>/<HH-MM-SS>.md` (create directories as needed)

2. Update the latest pointer:
   - `docs/reports/LATEST.md`
   - Contents must either:
     - include the full latest report, or
     - link clearly to the latest versioned report

3. Append an entry to the index:
   - `docs/reports/INDEX.md`
   - Each entry MUST include:
     - timestamp
     - report path
     - HEAD commit (or N/A)
     - fingerprint hash
     - 1–2 bullets summarizing what changed vs the previous report

---

## Anti-loop Rule (Stability Guarantee)

This workflow MUST NOT enter regeneration loops.

Rules:

- Reports generated by this workflow are allowed to modify `docs/reports/`
- Repository change detection (fingerprint comparison) MUST exclude `docs/reports/` from consideration
- The workflow MUST compute the fingerprint BEFORE writing a new report
- The fingerprint MUST NOT be recomputed after report generation
- A single execution may generate at most ONE report

If exclusion of `docs/reports/` is not technically possible in the execution environment, the workflow MUST:

- compute the fingerprint once
- generate the report
- terminate without attempting further comparison or regeneration

---

## Minimum Insight Rule (ENFORCED)

A valid Project Report MUST include:

- ≥1 architectural observation
- ≥1 explicit design trade-off
- ≥1 limitation or risk derived from structure

Reports missing these are INVALID.
