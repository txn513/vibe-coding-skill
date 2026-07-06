# Workflow Reference

Manage the full Vibe Coding delivery pipeline through structured, project-local
governance. This skill is a reusable control layer, not a store of business
knowledge. Project-specific decisions belong in `AGENTS.md` and `.agents/`.

## User Experience Contract

The user does not need to know script names, statuses, templates, or how to
decompose work. Accept a natural-language idea, problem, change, or question.
Inspect the project, infer the current stage, ask only for missing decisions
that materially affect scope or risk, and invoke the internal tools. Do not
make the user operate the command line unless explicitly requested.

When intent is unclear, create an intent record and guide discovery before
creating a spec. When enough evidence exists, proceed autonomously to the next
allowed step. Report the decision, artifact, blockers, and next action in
normal language.
When the user asks "what should we do next", answer with one governed next
action plus a short gate summary, why a later stage is not yet selected, and
one reasonable fallback action.
When the user says `Vibe 复盘这个问题`, treat it as a project retrospective
command: inspect the current project's artifacts, write back project-local
learnings first, then evaluate whether any generalized governance rule should
be promoted into the Skill.
When the issue maps to a known spec, route that phrase to:

```bash
python3 scripts/vibe.py retrospective <project_root> <spec_name>
```

Only ask the user for clarification when the spec or bug identity cannot be
determined from the current project context.
If `self_analyze` or a project retrospective discovers generalized governance
candidates, it may proactively ask a short confirmation question before
applying them. Discovery may be automatic; Skill-core modification may not.
When writing a retrospective, first classify the dominant failure mode. Prefer
the shared categories from the core Skill such as `single-point verified,
composed path missing`, `steady-state verified, time-state missing`, `happy-path
verified, degradation-path missing`, `component capability exists, routing or
selection wrong`, `rule exists, but is not bound to a gate or command`, or
`evidence exists, but does not prove the claimed behavior`.


## Workflow Overview

```
Discover → Design → Spec → Plan → Execute → Verify → Review → Release → Observe → Retro
  │                  │                                │                         │          │
  └─ Init ──┘        └────── Manage Specs ────────────┘                         │          │
  (新项目)                 Refresh Context                                       │          │
                                                                                 │          │
                                                                   Self-Analyze ←┘          │
                                                                        │                     │
                                                                   Self-Upgrade ─────────────┘
```

At any point, a work item may become `blocked`, `cancelled`, or `superseded`.
Requirement changes invalidate and archive downstream artifacts. Risk profiles
determine which gates apply.

## Internal Dispatcher

Prefer `scripts/vibe.py` for common operations after interpreting the user's
language:

```bash
python3 scripts/vibe.py status <project_root>
python3 scripts/vibe.py intent <project_root> <name>
python3 scripts/vibe.py spec <project_root> <name> --risk medium
python3 scripts/vibe.py advance <project_root> <name> in-progress
python3 scripts/vibe.py evidence <project_root> <name> verify passed \
  --command <project-verification-command>
python3 scripts/vibe.py evidence <project_root> <name> verify passed --configured
python3 scripts/vibe.py evidence <project_root> <name> verify passed \
  --purpose reproduction
python3 scripts/vibe.py risk <project_root> <name> high --reason "scope changed"
python3 scripts/vibe.py rule-status <project_root> <rule> adopted \
  --reason "owner approved"
python3 scripts/vibe.py review-decision <project_root> <name> approved \
  "decision basis" "evidence checked" --reviewer NAME
python3 scripts/vibe.py doctor <project_root>
python3 scripts/vibe.py migrate <project_root> --apply
```

### Verify commands (standalone, no commit)

```bash
# Default: run full suite (commands.verify)
python3 scripts/vibe.py verify <project_root>

# Fast scoped verification (commands.verify_scope)
python3 scripts/vibe.py verify <project_root> --scope

# Explicit full suite including integration/e2e (commands.verify_full)
python3 scripts/vibe.py verify <project_root> --full
```

Use `vibe verify` when you want to check test health without committing
(e.g. after a series of `--no-verify` commits, or before deciding whether
to commit). Falls back to `verify` if `verify_scope` or `verify_full` is
not configured separately.

### Commit commands (Rule 53)

```bash
# Default: verify_scope (if configured) or verify, then git commit
python3 scripts/vibe.py commit <project_root> -m "describe this batch"

# Split a dirty tree into focused commits
git add <paths>  # stage only the files for this logical unit
python3 scripts/vibe.py commit <project_root> --staged -m "task N"

# Or specify paths directly
python3 scripts/vibe.py commit <project_root> --paths a.py,b.py -m "task N"

# Batch commit pattern:
#   Intermediate commits (skip verify for speed)
python3 scripts/vibe.py commit <project_root> --staged --no-verify -m "task N"
#   Final commit in batch (run full suite)
python3 scripts/vibe.py commit <project_root> --full-verify -m "batch complete"

# Escape hatch: skip Rule 53 gate entirely (docs-only, hotfix)
python3 scripts/vibe.py commit <project_root> --no-verify -m "docs: update README"
```

These commands are an implementation interface for Codex, not required user
knowledge. Use specialized scripts where the dispatcher does not expose an
operation.

## Project Workflow Model

`.agents/workflow.json` is the project-local, versioned workflow manifest. It
contains only generic governance configuration: role assignments, low/medium/
high risk gate profiles, project-defined verification/release/observation
commands, and repository membership.

Specs record risk, owner, dependencies, and release group. Never put concrete
vulnerabilities, framework lore, business rules, or organization decisions
into this skill. Retrospective learnings remain project-local unless a human
deliberately promotes a generic pattern after evidence across projects.

## When to Use Each Script

### Project Setup

**`scripts/init_project.py`** — New project initialization:
```bash
python3 scripts/init_project.py <project_path> [--type generic|web|api|cli]
```
The default type is `generic`. Do not assume a language, framework, database, deployment target, or architecture. The generated files deliberately leave these decisions as `待确认`.

**`scripts/onboard_project.py`** — Onboard existing codebase:
```bash
python3 scripts/onboard_project.py <project_root> [--type generic|web|api|cli]
```

Onboarding creates `.agents/policy-sources.json` after inspecting known
instruction, contribution, CI, build, and project-local rule locations. The
inventory records source ownership and precedence without copying their
business content or guessing that two natural-language rules conflict.
It also refreshes `.agents/policy-differences.md`, a review-oriented summary of
which existing project sources still need confirmation before you trust the
governance picture. Each pending source includes a suggested landing zone such
as `.agents/workflow.json`, project rules, or an explicit conflict record.
In parallel it refreshes `.agents/policy-confirmations.md`, an editable draft
that turns those suggestions into a small decision worksheet instead of making
you start from a blank file. Each item also includes a candidate patch snippet
for `workflow.json`, a project rule draft, or an explicit conflict template.

When an actual conflict is found, record it explicitly:

```bash
python3 scripts/vibe.py policy-conflict-add <project_root> <conflict-id> \
  --topic "<topic>" \
  --sources "agents-md,agent-rule-security" \
  --severity high \
  --description "<why these instructions cannot both be followed>" \
  --scope "<spec-name>"
```

Resolve it only after the applicable rule is decided:

```bash
python3 scripts/vibe.py policy-conflict-resolve <project_root> <conflict-id> \
  --resolution "<chosen precedence and rationale>"
```

`high` open conflicts block affected specs at `spec-ready`; `medium` and `low`
conflicts remain visible warnings. Existing projects without an inventory stay
compatible and receive a doctor warning until scanned.
Scans directory, detects tech stack (language, framework, database, deployment, linter, test framework), and generates a pre-filled AGENTS.md.

### Design & Specification

**`scripts/create_intent.py`** — Discovery record for an unclear request:
```bash
python3 scripts/create_intent.py <project_root> <name>
```
Capture the problem, affected users, desired outcome, evidence, unknowns,
constraints, risks, and the decision to proceed, investigate, or stop.

**`scripts/create_design.py`** — Architecture design document:
```bash
python3 scripts/create_design.py <project_root> <design_name>
```
Use the generic boundary/contract/decision template. Add project-specific sections only inside the project document.

**`scripts/create_spec.py`** — Feature / Bug / Refactor spec:
```bash
python3 scripts/create_spec.py <project_root> <name> --risk medium
python3 scripts/create_spec.py <project_root> <name> --type bug --owner OWNER
python3 scripts/create_spec.py <project_root> <name> --type bug --regression-from SPEC
python3 scripts/create_spec.py <project_root> <name> --depends-on spec-a,spec-b
python3 scripts/create_spec.py <project_root> <name> --release-group GROUP
```

### Agent Interaction

**`scripts/generate_prompt.py`** — Generate ready-to-use Agent prompt from spec + context:
```bash
python3 scripts/generate_prompt.py <project_root> <spec_name> [--with-design] [--print-only]
```
Combines AGENTS.md + all project rules + project checklist + design + spec + plan into one prompt. Saves to `.agents/prompts/`. Do not infer that a project rule is irrelevant from filenames or technology guesses.

**`scripts/generate_plan.py`** — Implementation plan from spec:
```bash
python3 scripts/generate_plan.py <project_root> <spec_name>
python3 scripts/generate_plan.py <project_root> <spec_name> --force  # replace existing plan
```

### Specification Quality

**`scripts/validate_spec.py`** — Validate spec completeness before coding:
```bash
python3 scripts/validate_spec.py <project_root> <spec_name>
python3 scripts/validate_spec.py <project_root> --all       # validate all specs
```
Checks for placeholder text, missing sections, empty acceptance criteria. Returns pass/fail. **Run this before every `generate_prompt.py` call.**

**`scripts/set_status.py`** — Update spec status without editing markdown. This is the underlying implementation behind the user-facing `vibe advance` command; both are valid, but prefer the dispatcher for new scripts.
```bash
python3 scripts/set_status.py <project_root> <spec_name>              # show current
python3 scripts/set_status.py <project_root> <spec_name> spec-ready   # update
python3 scripts/set_status.py <project_root> <spec_name> done --force \
  --reason "documented exception" --actor NAME --role override_approver
```
Valid statuses include `draft`, `spec-ready`, `in-progress`, `review`,
`released`, `blocked`, `done`, `cancelled`, and `superseded`. Gates come from the spec's
risk profile. Dependencies must be done before implementation. High-risk work
can require a clean Git worktree and separation between builder and reviewer.
Forced or terminal transitions require a reason and are audited.

**`scripts/spec_amend.py`** — Record a requirements change mid-implementation:
```bash
python3 scripts/spec_amend.py <project_root> <spec_name> "变更描述"
```
Creates an amendment log file (`.agents/specs/<name>-amendments.md`) and appends a change table to the spec. Tells you to manually update affected sections (acceptance criteria, constraints, scope).
It also resets the spec to `draft` and archives the old plan and prompt because they were generated from superseded requirements.
The amendment marks risk confirmation as `pending`. Reconfirm the project
decision before returning to `spec-ready`:
```bash
python3 scripts/confirm_risk.py <project_root> <spec_name> medium \
  --reason "affected scope reviewed"
```
Risk increases and reductions both require a reason. The Skill enforces the
decision record; it does not infer the project's correct risk.

### UI Design Contracts

**`scripts/create_ui_contract.py`** — Create a project-local UI contract draft
from an external design source, screenshot, generated prototype, or manual
brief:
```bash
python3 scripts/create_ui_contract.py <project_root> <spec_name> \
  --source-type opendesign \
  --source-artifacts design/opendesign/DESIGN.md \
  --generated-by "Open Design" \
  --model-capability text-only
```

For existing UI redesign work, create the stricter preserve/replace contract:
```bash
python3 scripts/create_ui_contract.py <project_root> <spec_name> \
  --redesign \
  --source-type opendesign \
  --source-artifacts design/opendesign/
```

The dispatcher exposes these as:
```bash
python3 scripts/vibe.py ui-contract <project_root> <spec_name>
python3 scripts/vibe.py ui-redesign-contract <project_root> <spec_name>
```

Use these contracts to convert tool outputs into source artifacts, layout,
component mapping, states, accessibility expectations, numbered `UI-AC`
clauses, and evidence plans. Do not treat generated screenshots, HTML, or
design-tool exports as accepted requirements unless the relevant promises are
mapped into the contract and later verified with evidence.

Adapter names are not style names. Do not infer that Open Design, Penpot,
Figma, screenshots, or another source implies a specific component system,
visual language, animation behavior, icon strategy, shadow model, or design
system. Read project-local guidance first and record any visual prohibitions or
design constraints in the contract's `Project UI Constraints` section. If the
source artifact conflicts with AGENTS.md or adopted project rules, the project
constraint wins and the conflict must be resolved before implementation.

For a new project with a user-visible UI, surface this design-first path before
the first implementation spec:

1. Clarify product intent and target user task.
2. Identify primary flows and first screens/routes.
3. Decide whether to use a project-local design adapter such as Open Design,
   Penpot, Figma, screenshots, or a manual brief.
4. Create a UI Design Contract when visual structure, states, accessibility, or
   acceptance criteria need to survive into implementation.
5. Create the implementation spec from the contract and map UI promises to
   `UI-AC` clauses.

This is an early workflow prompt, not a mandatory artifact for every project.
If the user chooses a code-first spike or the project is non-UI, record that
tradeoff in the intent or spec and continue through the normal workflow.

When iterating on an existing UI design, treat the request as versioned even if
the user only says "continue iterating" and does not explicitly say "do not
overwrite." Do not overwrite the previous contract or source artifacts without
preserving history. Create a new contract version, archive the replaced
contract, or append a design revision section that records:

- baseline version or source artifact
- new stable version ID (`v2`, `v3`, or project-defined equivalent)
- changed items
- preserved items
- abandoned items
- rollback target: the prior contract/source artifact or archive path that can
  restore the previous design version
- affected `UI-AC` or behavior AC
- spec/plan/implementation impact
- updated visual or behavior evidence needs

If the design revision changes a spec that is already planned, in progress,
under review, or released, use `vibe amend` or create a follow-up spec. Do not
silently mutate design guidance that downstream implementation or evidence was
already bound to.

Suggested natural-language trigger:

```text
Vibe，基于当前 UI Design Contract 继续迭代一版设计。
```


## Refresh a plan after spec or context change

Plans are bound to two digests and can go stale for different reasons. `vibe doctor` and `vibe next` distinguish them and recommend the matching refresh command:

| What changed                            | Stale digest     | Doctor message                                          | Refresh command                |
|-----------------------------------------|------------------|---------------------------------------------------------|--------------------------------|
| Spec frontmatter or body                | `规格摘要` | `stale plan (spec digest mismatch); regenerate or run vibe plan <root> <spec> --force` | `vibe plan <root> <spec> --force`        |
| adopted rule, `AGENTS.md`, checklist    | `上下文摘要` | `stale project guidance; run ... --refresh-context`     | `vibe plan <root> <spec> --refresh-context` |
| No plan file yet                        | n/a              | `Plan 缺失`                                              | `vibe plan <root> <spec> --force`        |

Use `--force` when the spec itself changed: the plan's spec digest no longer matches the current spec, so the steps need to be re-bound. Use `--refresh-context` when only project guidance changed: the steps still match the spec, but the captured context digest is out of date.

```bash
# Spec changed (frontmatter, body, status, dependencies, scope, AC)
vibe plan <root> <spec> --force
# Project guidance changed (adopted rules, AGENTS.md, checklist)
vibe plan <root> <spec> --refresh-context
```

The previous plan is archived under `.agents/archive/<spec>/plans/`. After a refresh, re-run `vibe next` to confirm the new plan is bound to the current snapshot before any advance.

### Verification

**`scripts/record_evidence.py`** — Record project-defined verification or release evidence:
```bash
python3 scripts/record_evidence.py <project_root> <spec_name> verify passed "evidence"
python3 scripts/record_evidence.py <project_root> <spec_name> release not-applicable "reason"
python3 scripts/record_evidence.py <project_root> <spec_name> verify passed \
  --actor NAME --role builder --command <real-project-command>
python3 scripts/record_evidence.py <project_root> <spec_name> verify passed \
  --actor NAME --role builder --configured
python3 scripts/record_evidence.py <project_root> <spec_name> observe passed \
  "production observation" --actor NAME --role observer
```
Results are `passed`, `failed`, or `not-applicable`. Prefer executing the real
project command. Evidence captures its exit code and bounded output and is
bound to the current spec digest, project-guidance digest, Git commit, source
snapshot, actor, and role. Common credential-shaped values are redacted before
output is persisted. Later changes invalidate stale evidence.
If commands are configured for a phase, all configured command fingerprints
must appear in the evidence; a manual claim cannot satisfy that gate.

Bug fix evidence must address both directions:
- Reproduction: the bug was confirmed present before the fix.
- Fix + regression: the bug is resolved and original behavior is preserved.

Record these as ordered, separate evidence entries with `--purpose reproduction`
and `--purpose fix-regression`. Reproduction evidence may retain its pre-fix
source snapshot. Fix-regression evidence must match the current source snapshot
and configured verification commands. When the bug is a regression, the
`--regression-from` field links it to the originating spec so `doctor` can
cross-check.

Test coverage rule: when a change can affect existing behavior, prefer an
automated regression test. For bug fixes, boundary-sensitive changes, and
stateful flows, capture a failing-before / passing-after test or document the
equivalent manual or command-based verification if automation is impractical.

For project-local retros and testing rules, map recurring bugs back to a small
failure-mode vocabulary when possible. This helps weaker models reuse existing
patterns instead of inventing a fresh explanation every time.

**`scripts/generate_review.py`** — Independent review context:
```bash
python3 scripts/generate_review.py <project_root> [spec_name]
```
The reviewer must submit `approved` or `changes-requested` with a concrete
basis and the evidence checked. Reviews are bound to the current spec,
governing context, Git identity, and named reviewer.

**`scripts/record_review.py`** — Record a structured review decision:
```bash
python3 scripts/record_review.py <project_root> <spec_name> approved \
  "decision basis" "evidence checked" --reviewer NAME
```
Use this instead of editing the conclusion manually. It writes a recomputable
decision-integrity marker and the reviewer role used by status gates.

### Risk-based rule readiness

Spec-ready is gated by a project-configured list of required rule stems per
risk level. The default is empty (no project-level requirement), but projects
can declare their own list:

```json
"risk_required_rules": {
  "high": ["security", "auth"],
  "medium": ["security"],
  "low": []
}
```

When a spec advances to `spec-ready`, the gate checks every stem listed under
its risk level: the file `.agents/rules/<stem>.md` must exist and its frontmatter
status must be `adopted` (not `proposed` or `deprecated`). When the gate fails,
the spec is held back and the Agent receives one message per missing or
non-adopted stem, so it can either fill the gap or remove the stem from the
project's required list. The Skill never assumes a specific filename — the
project's declared stems are the source of truth.

The Skill never silently infers which rules a project "should" have; it only
enforces the list the project itself declared. Adding or removing stems is a
deliberate workflow.json edit, not an automated inference (Rule 15 extension).

### Maintenance

**`scripts/archive_status.py`** — Find and archive stale `.agents/` artifacts:

```bash
python3 scripts/archive_status.py <project_root>            # dry-run preview
python3 scripts/archive_status.py <project_root> --apply    # actually move files
# or via the outer CLI:
vibe archive-stale <project_root>
vibe archive-stale <project_root> --apply
```

Three kinds of staleness are checked, each with its own threshold in
`workflow.json` under `archive.thresholds_days`:

- `evidence` (default 90 days): verify / observe / release evidence for specs
  whose status is `released`, `done`, `superseded`, or `cancelled`.
- `rule_unreferenced` (default 180 days): rule files whose filename stem does
  not appear in any spec, plan, retro, intent, or design document.
- `spec_untouched` (default 365 days): spec files for `cancelled` or
  `superseded` specs whose frontmatter `更新:` field is older than the
  threshold.

The script never recurses into `.agents/archive/` and never deletes files;
`--apply` moves them into `.agents/archive/<UTC-timestamp>/<original-relative-path>`
with a `manifest.json` describing each move. `archive.scan_paths` and
`archive.exclude_paths` in `workflow.json` let a project tune which
directories participate without editing the Skill.

The command is always explicit. `doctor` and `next` only surface the count as
an advisory; the Skill never archives silently (Rule 45).

**Stage-stall observability** — A spec that stays in the same stage longer than its risk SLA appears as a low-priority advisory after `vibe status` and `vibe next`. The thresholds live in `workflow.json` under `stage_stall_sla`:

```json
"stage_stall_sla": {
  "low_hours": 72,
  "medium_hours": 24,
  "high_hours": 8
}
```

The entered-at timestamp is read from `.agents/activity.md`, which `set_status` already auto-writes on every status change. Specs without an activity entry are skipped (the Skill cannot reason about duration without a timestamp). The advisory never blocks `vibe advance`; it exists so the Agent can notice a stuck spec and decide whether to advance, amend, or cancel it (Rule 46).

**`scripts/doctor_project.py`** — Check schema, dependencies, and stale artifacts:
```bash
python3 scripts/doctor_project.py <project_root>
```

**`scripts/migrate_project.py`** — Preview or apply non-destructive migration:
```bash
python3 scripts/migrate_project.py <project_root>
python3 scripts/migrate_project.py <project_root> --apply
```
Applied metadata edits are backed up. Migration may add generic fields and
schema structure; it must not invent project decisions.

**`scripts/project_status.py`** — Holistic project overview:
```bash
python3 scripts/project_status.py <project_root>
python3 scripts/vibe.py next <project_root>
```
`status` shows the overview. `next` returns one prioritized, gate-aware action
with its reason and blocker. It accounts for dependencies, required plans,
current evidence, review approval, release/observation gates, and retros. When a
plan is stale, `next` classifies the staleness (spec digest vs context digest vs
missing) and prints the matching refresh command alongside the recommended
action, so the agent does not advance against a plan that is no longer bound to
the current snapshot.

**`scripts/refresh_context.py`** — Update AGENTS.md from current codebase state:
```bash
python3 scripts/refresh_context.py <project_root>
```
Only fill unconfirmed fields automatically. Preserve confirmed project decisions and stage detected disagreements in `.agents/context-refresh.md` for review. Also checks whether the phase-gates section needs updating from the latest Skill template; if so, it updates the section automatically and preserves any project-level overrides.

**`scripts/update_agents.py`** — Update project's phase-gates section from the latest Skill template:
```bash
python3 scripts/update_agents.py <project_root>
python3 scripts/update_agents.py <project_root> --force   # force update even if version matches
# or via the outer CLI:
vibe update-agents <project_root>
vibe update-agents <project_root> --force
```

Reads the latest `agents-phase-gates.md` template from the Skill, extracts the
`## 阶段强制规范（Phase Gates）` section, and replaces or appends it in the
project's AGENTS.md. The section is versioned with a
`<!-- vibe:phase-gates-version: <hash> -->` marker so the Skill can detect
drift. If the project has a `## 阶段覆盖声明（Phase Gates Override）` section,
the merge preserves project overrides — project-level declarations take
precedence over Skill defaults, and the merged section annotates the override.
`vibe context-refresh` also calls this automatically, so the phase-gates
section stays current without a separate command in most cases.

**`scripts/sync_rules.py`** — Sync project rules with latest skill templates:
```bash
python3 scripts/sync_rules.py <project_root>             # show diff
python3 scripts/sync_rules.py <project_root> --apply      # copy missing, stage updates
python3 scripts/sync_rules.py <project_root> --apply --force  # backup then replace
```
Compare `.agents/rules/` with the skill templates. Never overwrite a changed project rule with plain `--apply`; stage the new template under `.skill-updates/`. Use `--force` only after review; it creates a backup first.

**`scripts/manage_specs.py`** — Multi-spec management:
```bash
python3 scripts/manage_specs.py <project_root>              # list all
python3 scripts/manage_specs.py <project_root> --conflicts   # detect conflicts
python3 scripts/manage_specs.py <project_root> --priority    # suggest order
```

**`scripts/portfolio_status.py`** — Summarize multiple project roots:
```bash
python3 scripts/portfolio_status.py <project_root> [<project_root> ...]
python3 scripts/portfolio_status.py <roots...> --release-group GROUP
```
This provides cross-project visibility and release-group readiness reporting.
It does not perform transactional deployment or distributed rollback. Keep
each repository's facts local and use an external delivery system when atomic
multi-repository release coordination is required.

### Release & Retrospective

**`scripts/generate_changelog.py`** — Changelog from completed specs:
```bash
python3 scripts/generate_changelog.py <project_root> [--version v1.2.0]
python3 scripts/generate_changelog.py <project_root> --release-group GROUP
python3 scripts/generate_changelog.py <project_root> --version v1.2.0 --force
```
Existing changelogs are not overwritten unless `--force` is used; forced replacement creates a backup.

**`scripts/create_retro.py`** — Feature retrospective:
```bash
python3 scripts/create_retro.py <project_root> <spec_name>
```

### Self-Improvement

**`scripts/self_analyze.py`** — Analyze retros to find project-local improvement opportunities:
```bash
python3 scripts/self_analyze.py <project_root> [--output report.md]
```
Scans all `.agents/retros/` files, identifies recurring patterns in Agent mistakes, missing rules, and missed constraints. Generates suggestions for this project's `.agents/` guidance only.

**`scripts/self_upgrade.py`** — Apply self-analysis suggestions to the PROJECT (not the skill):
```bash
python3 scripts/self_upgrade.py --dry-run    # preview changes
python3 scripts/self_upgrade.py --apply      # apply to project
python3 scripts/self_upgrade.py --apply --auto --prune  # apply + prune
```
Adds checklist items to `.agents/checklists/custom.md`, creates rule files in `.agents/rules/`, and adds spec hints. **All changes are project-local.** The skill's own SKILL.md and templates/ remain as the universal baseline unchanged.
Every suggestion is classified as `governance`, `project`, or `external`
before application. `self_upgrade.py` only applies `project` knowledge under
the current project's `.agents/`; other classes are blocked and routed to
human Skill review or external integration.

Generated rules start as `proposed` and are excluded from execution prompts
and project-context freshness until explicitly adopted. Legacy project rules
without lifecycle metadata remain active:
```bash
python3 scripts/rule_status.py <project_root> <rule_name> adopted \
  --reason "project owner approved"
python3 scripts/vibe.py rule-status <project_root> <rule_name> deprecated \
  --reason "rule no longer applies"
```

**`scripts/knowledge_gate.py`** — Classify candidates and audit Skill boundaries:
```bash
python3 scripts/knowledge_gate.py classify "candidate text" --target .agents/rules/
python3 scripts/knowledge_gate.py audit <skill_root> --project-root <project_root>
python3 scripts/vibe.py boundary <project_root>
```
Absolute project paths and known project identifiers in Skill files are hard
violations. Concrete URLs, endpoints, and SQL details are review warnings
because they may be legitimate generic examples. A warning is not promoted
automatically; a human decides whether it is governance, project knowledge, or
an external integration.

**`scripts/self_prune.py`** — Prune stale project-level rules and checklist items:
```bash
python3 scripts/self_prune.py <project_root> --dry-run    # preview
python3 scripts/self_prune.py <project_root> --apply       # execute
```
Identifies project-level checklist items (`.agents/checklists/custom.md`) and auto-generated rule files that have become irrelevant. Builtin items and skill-level files are never touched. Applied removals are archived for recovery.

**Typical self-improvement cycle (project-local, safe):**
1. Complete 2-3 features with retros
2. Run `self_analyze.py` to find patterns
3. Run `self_upgrade.py --dry-run` to preview additions (→ .agents/checklists/custom.md)
4. Run `self_prune.py --dry-run` to preview removals
5. Run `self_upgrade.py --apply --prune` to add + remove in one pass
6. Before each `generate_prompt.py`, run `validate_spec.py` to catch placeholders
7. Update spec status with `vibe advance` (or the underlying `scripts/set_status.py`) as work progresses
8. Project accumulates its own knowledge; skill stays as the universal baseline
9. If a pattern repeats across 3+ projects, manually promote it to the skill

## Governance Rules

1. Treat Agent output as a proposal until required project gates pass.
2. Bind plans, prompts, evidence, and reviews to evaluated versions.
3. Use actual command execution for mechanical checks whenever possible.
4. Validate both actor identity and declared role; do not allow one actor to
   satisfy separated high-risk roles.
5. Do not silently bypass a gate; overrides require actor, role, and reason.
6. Archive superseded downstream artifacts instead of mutating history.
7. Keep project truth in the project and this skill generic and compact.
8. Prefer project detection and references over embedding domain catalogs.
9. Migrate old projects explicitly and diagnose integrity before resuming.
10. Retire stale project guidance so self-improvement does not grow forever.
11. Classify every proposed improvement before placement; uncertainty defaults
    to project-local.
12. Never auto-promote a single project's learning into the Skill.
13. Keep generated rules inactive until a project owner adopts them.
14. Reconfirm risk after requirement amendments before implementation resumes.
15. Treat external UI design tools as adapters; convert their output into
    project-local contracts, acceptance criteria, and evidence mapping before
    implementation or acceptance.
16. For new user-visible UI projects, prompt for product/UX/UI design guidance
    before the first implementation spec; allow explicit code-first or non-UI
    opt-outs with the tradeoff recorded.
17. Do not infer a design adapter as a visual style; project-local UI
    constraints and prohibitions outrank adapter defaults.
18. Version UI design iterations by default; record baseline, stable version
    ID, rollback target, changes, preserved and abandoned decisions, affected
    acceptance criteria, and evidence updates.

## Phase Checklists

Use these as generic prompts. Record project-defined verification and release outcomes with `record_evidence.py`; do not treat the checklist wording as project-specific answers.

### Pre-Design Checklist
```
□ Problem is clearly understood
□ Existing architecture is reviewed
□ Performance/scale requirements are known
□ Security/compliance requirements are identified
```

### Spec Review Checklist (review spec before coding starts)
```
□ Intent is clear and unambiguous
□ Success criteria are measurable
□ All placeholder text has been replaced
□ Happy path acceptance criteria are concrete (not placeholder)
□ Edge cases are covered
□ Error handling is specified
□ Constraints are explicit (tech + business + out-of-scope)
□ Scope is defined (new files, modified files, don't-touch files)
□ Non-functional requirements are specified (performance, security, accessibility)
□ No contradictions between constraints and acceptance criteria
```

### Pre-Code Checklist
```
□ Spec is complete with clear intent
□ Constraints are explicit (tech + business + out-of-scope)
□ Acceptance criteria cover happy path, edge cases, errors
□ Dependencies and prerequisites defined by the project are ready
□ AGENTS.md and .agents/rules/ are up to date
□ Design doc exists for complex features
□ Check .agents/checklists/custom.md for project-specific checks
```

### Implementation Checklist
```
□ The project's required implementation checks pass
□ Naming follows project conventions
□ Project security and data-handling rules are followed
□ Failure behavior follows project rules
□ Required verification accompanies the change
□ Scope and dependency changes are explicitly authorized
□ Check .agents/checklists/custom.md for project-specific checks
```

### Review Checklist
```
□ All acceptance criteria are implemented
□ Changed behavior has regression coverage or a documented equivalent check
□ Verification evidence satisfies the project standard
□ Temporary implementation artifacts have been removed
□ The final change set matches the approved scope
□ Independent review context has been generated
```

### Deploy Checklist
```
□ Project-defined release gates pass
□ State and data changes have a recovery strategy
□ Required production observation is ready
□ Rollback or recovery evidence is confirmed
□ Release strategy matches project risk requirements
```

## Key Principles

1. **Spec before code.** Unclear intent is the #1 cause of vibe coding failures.
2. **Design before spec (for complex features).** Data model disagreements cause the most rework.
3. **Generate prompts, don't hand-assemble.** Use generate_prompt.py.
4. **Constraints, not implementation.** Describe what and what not to touch.
5. **One feature per session.** One spec → one implementation → one review.
6. **Independent review.** Always use a fresh Agent session.
7. **Context rots.** Run refresh_context.py weekly.
8. **Retro or repeat mistakes.** After every feature, capture learnings.
9. **Onboard before coding on existing projects.** Run onboard_project.py first.
10. **Project knowledge stays in the project.** self_upgrade writes to `.agents/checklists/custom.md` and `.agents/rules/` — never to the skill's own files. The skill is the universal framework; each project grows its own specific checks and rules.
11. **Promote process only.** Cross-project evidence may improve universal workflow mechanics, but never promote project-specific technology, architecture, security, or business answers into the skill.
12. **Gate every transition.** Before advancing a spec's status, run `vibe next` to verify all gates are met. After advancing, run `vibe status` to report the result. No silent transitions.
