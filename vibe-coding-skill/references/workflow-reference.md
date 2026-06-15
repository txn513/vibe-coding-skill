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

**`scripts/set_status.py`** — Update spec status without editing markdown:
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

### Maintenance

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
current evidence, review approval, release/observation gates, and retros.

**`scripts/refresh_context.py`** — Update AGENTS.md from current codebase state:
```bash
python3 scripts/refresh_context.py <project_root>
```
Only fill unconfirmed fields automatically. Preserve confirmed project decisions and stage detected disagreements in `.agents/context-refresh.md` for review.

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
7. Update spec status with `set_status.py` as work progresses
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
