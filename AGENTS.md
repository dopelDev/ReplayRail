AGENTS.md

AGENT_BOOTSTRAP_TEMPLATE_V2

Use this template as a neutral starting point when creating a new repository.
Fill all required fields before first agent action.

REQUIRED FIELDS:

- repo_name:
- owner_or_team:
- project_type:
- primary_language:
- runtime:
- package_manager:
- test_command:
- lint_or_format_command:
- ci_path:

PURPOSE:

- what the repo does:
- business outcome enabled:
- why an AI agent is useful here:

PROJECT CONTEXT:

- domain_areas: area1, area2, area3...
- intended_users:
- critical_integrations:
- data_storage:
- deployment_mode: local | container | cloud | hybrid

BOOTSTRAP CHECKLIST:
[ ] Define all required fields
[ ] Define 3 to 6 key responsibilities/areas
[ ] Confirm global rules
[ ] Confirm whether AGENT MODE variants are allowed
[ ] Add workflow path list under AGENTS.d/workflows/
[ ] Add any repo-specific prohibitions (secrets, destructive commands, approvals)

GLOBAL RULES:

- Do not assume intent.
- Run workflows only when explicitly requested.
- Workflow execution always requires clear confirmation.
- Prefer analysis before modification.
- No side effects without user approval.
- Do not invent new workflows.
- Never run workflows implicitly.
- Separate facts from recommendations clearly.

AGENT MODE STATE (set exactly one to enabled):

- analyze_mode = enabled
- action_plan_mode = disabled
- agent_mode = disabled

Mode behavior (select exactly one):

- analyze_mode
  - Read/search repo context, inspect commits, and reason.
  - No file edits, no deletes, no commands with side effects.
  - If user later asks for any change, request mode switch to Action Plan or Agent.

- action_plan_mode
  - Build and present an execution plan before edits.
  - List each file operation (create/modify/delete) with exact paths and ask confirmation before each operation.
  - No file changes until plan is approved and user confirms the operation.

- agent_mode
  - Execute approved changes directly (including code/config/docs edits).
  - Still ask before Git operations that modify history or publish (`add`, `commit`, `push`, `reset`, `rebase`, branch/tag ops).
  - No broad, undeclared actions; keep changes scoped to confirmed request.

WORKFLOW INDEX (fill if used):

- CreateCommit -> AGENTS.d/workflows/CreateCommit.md
- GenerateProjectReport -> AGENTS.d/workflows/GenerateProjectReport.md

SAFE EDIT GUIDE (first-pass):

- start with docs and metadata only
- avoid architecture-changing edits until required fields + constraints are set
- pause for confirmation before commands with destructive scope

SETUP FOOTPRINT:

- setup flow:
- build flow:
- run flow:
- test flow:
- known assumptions:
- known risks:
