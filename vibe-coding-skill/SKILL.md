---
name: vibe-coding
description: Vibe Coding project-governance skill covering discovery through retirement. Use when the user describes an idea, change, defect, refactor, delivery problem, or project status question and Codex should translate it into the appropriate workflow; initialize or onboard projects; create and validate intents, designs, specs, plans, prompts, reviews, evidence, releases, changelogs, and retros; enforce risk-, role-, dependency-, Git-, and version-aware gates; migrate workflow schemas; diagnose integrity; summarize multiple projects; or evolve project-local guidance without adding project-specific knowledge to the skill.
---

# Vibe Coding

Guide delivery with a small project-local governance layer. Keep business,
architecture, security, and technology decisions in the project, never here.

## Interaction Contract

Accept natural-language ideas, defects, changes, or status questions. The user
does not need to know commands, statuses, templates, or task decomposition.

1. Inspect the repository and `.agents/` state.
2. Infer the current stage and risk.
3. Ask only for decisions that materially affect intent, scope, ownership, or
   risk.
4. Execute the next allowed step internally.
5. Report the artifact created, blockers, evidence, and next action.

If intent is unclear, use discovery before creating a spec. If the project is
not initialized, initialize a new project or onboard an existing repository.
After onboarding or resuming a project, diagnose workflow integrity and provide
one prioritized next action with its reason and blockers. Do not dump a generic
checklist when one governed action is sufficient.

When the user says `Vibe 复盘这个问题` or an equivalent phrase, treat it as a
project retrospective trigger. Reconstruct the issue from the current project's
specs, evidence, reviews, retros, rules, and relevant docs; then produce two
outputs:

1. project-local updates for the current repository
2. Skill upgrade candidates, but only after classifying each finding as
   `project`, `governance`, or `external`

Project-local learnings should be written back in the current project first.
Only generalized governance findings may be promoted into the Skill after a
boundary check.
When such candidates exist, the Agent may proactively ask a short confirmation
question such as `发现 2 条可能的 Skill 治理升级候选，是否应用？`, but it must
not modify the Skill core until the user explicitly confirms.
When the current issue can be mapped to a concrete spec, prefer executing the
project retrospective action for that spec. The canonical action is:
`python3 scripts/vibe.py retrospective <project_root> <spec_name>`.
If the target spec is ambiguous, ask only for the missing spec or bug identity.

During a retrospective, classify the primary failure mode before proposing a
fix. Prefer a small, reusable taxonomy:

- single-point verified, composed path missing
- steady-state verified, time-state missing
- happy-path verified, degradation-path missing
- component capability exists, routing or selection wrong
- rule exists, but is not bound to a gate or command
- evidence exists, but does not prove the claimed behavior

If none fit, state the mismatch explicitly instead of forcing a category.

## Minimal Workflow

```text
Discover → Spec → Plan? → Execute → Verify → Review? → Release? → Observe? → Done
```

Question marks are controlled by the risk profile:

- `low`: localized, reversible, and no durable contract or sensitive-state
  change.
- `medium`: normal user-visible or multi-module work.
- `high`: irreversible change, durable data/contract migration, privileged
  access, production infrastructure, or project-defined critical risk.

Default to `medium` when evidence is insufficient. Keep the low-risk path
short; do not manufacture artifacts for skipped gates.

Use design documents only when boundaries, contracts, data flow, migration, or
multiple implementation approaches need a durable decision. Do not create
artifacts merely because a template exists.

## Core Rules

1. Treat Agent output as a proposal until required gates pass.
2. Bind plans, prompts, evidence, and reviews to the requirement version,
   durable project policy, and relevant source snapshot.
3. Ignore mutable workflow status and role assignments when computing
   requirement/policy freshness; they must not cause false invalidation.
4. Execute configured project commands for mechanical checks. A written claim
   cannot replace configured command evidence.
5. Validate actor and declared role. High-risk separated roles must use
   different identities.
6. Require actor, `override_approver` role, and reason for every forced
   transition.
7. Archive replaced or superseded evidence and downstream artifacts.
8. Redact common credential-shaped values before persisting command output.
9. Keep retrospective learning project-local. Add only evidence-backed rules,
   mark them proposed until adopted, and prune stale guidance.
10. For bug fixes: require evidence that the bug reproduced before the fix and
    no longer reproduces after. When a bug is a regression from a prior change,
    mark the regression source; review the original spec's retro for root causes.
11. When a change can affect existing behavior, require regression coverage or
    an explicit equivalent verification path. Prefer adding the test with the
    fix rather than deferring validation to a later cleanup.
12. When a flow contains multi-step fallback or degradation paths, verify not
    only that each level works independently, but that failure of an upstream
    level actually routes execution to the intended downstream level, and that
    the terminal fallback remains usable when higher levels fail.
13. When behavior depends on time-sensitive or freshness-sensitive state such
    as cache TTL, token expiry, propagation delay, or refresh windows, verify
    at least three states: valid, expired or stale, and recovered after refresh
    or re-resolution.
14. When validation spans multiple components or boundaries, require a composed
    path check rather than only per-function checks. If a user choice, frontend
    branch, backend endpoint, adapter, or fallback target can change the
    effective behavior, verify the end-to-end path and confirm each critical
    handoff preserves the intended semantics.
15. When a spec touches fallback chains, expiry-sensitive state, cross-component
    selection paths, or state-changing frontend requests, the Agent must check
    whether the project's testing rules already define the verification method.
    If the relevant testing rule is still unspecified, the Agent must pause
    before claiming `verify` is complete and either record the project-local
    rule or explicitly surface the missing rule as a blocker.
16. During a retrospective triggered inside a project, the Agent must first
    attempt to update the project's own rules, docs, retros, or testing policy
    before proposing a Skill-core change. A Skill update is allowed only for
    the generalized governance remainder after project-specific detail has been
    stripped away.
17. `self_analyze` and project retrospectives may discover Skill-upgrade
    candidates automatically, but discovery is not authorization. They may
    surface candidates proactively, yet they must not change Skill-core files
    without an explicit user confirmation to apply them.
18. Treat generated project rules as `proposed` until explicitly adopted.
    Only adopted rules participate in prompts and context freshness.
19. Reset risk confirmation after every requirement amendment. Do not return
    to `spec-ready` until the risk level and reason are explicitly confirmed.
20. Classify every improvement as `governance`, `project`, or `external`
    before placing it. Only governance mechanisms may enter the Skill;
    project facts stay under the project's `.agents/`; external capabilities
    stay in project configuration or integrations. Never promote knowledge
    from one project into the Skill automatically; generic governance
    candidates require explicit human review and a boundary audit.
21. Do not silently expand into deployment orchestration, monitoring, issue
    tracking, or business-domain knowledge. Integrate external systems instead.
22. **Stage-transition gate**: Before advancing any spec's status, the Agent must
    run `vibe next` (or equivalent check) to confirm all gates for the target
    status are satisfied. After advancing, the Agent must run `vibe status` (or
    equivalent) to report the updated state. No status transition may happen
    silently without a preceding gate check and a following status report.
23. Use one active writer per spec. Parallelize through separate specs or
    worktrees instead of adding distributed locking to this Skill.
24. On existing projects, inventory policy sources before proposing changes.
    Existing project rules outrank Skill defaults. Do not infer semantic
    conflicts from keywords; record conflicts explicitly with sources, scope,
    severity, and resolution. Unresolved high-risk conflicts block affected
    specs from becoming `spec-ready`.
25. Retrospective writeups should name the dominant failure mode in a compact,
    reusable way before listing fixes. Prefer the shared failure taxonomy when
    it fits so that later `self_analyze` runs can aggregate patterns across
    multiple retros.
26. **Out of Scope must be tracked**: Every entry in a spec's Out of Scope
    section must be tagged before the spec reaches `done` with one of:
    (a) included in this spec, (b) handed off to a follow-up spec with that
    spec's ID recorded, or (c) explicitly abandoned with no planned follow-up.
    Items tagged as follow-up that remain without a corresponding spec beyond
    one iteration cycle must be explained in the retro.
    **Storage-cleanup sub-rule**: When a spec introduces a new storage location,
    data path, database file, or serialization format, the Out of Scope section
    must also include cleanup, disposal, or deprecation of the previous storage
    location. The verify evidence must confirm the old location is no longer
    referenced by production code and, when applicable, that its data is
    migrated or the file is removed.
27. **User guide must stay current**: Whenever a new command, trigger, capability,
    or rule is added to the Skill, [references/user-guide.md](references/user-guide.md)
    must be updated to reflect it. The user guide is the user-facing reference
    for all natural-language triggers.
28. **Verify must include user-perceivable evidence**: For any feature spec
    advancing to `done`, the verify evidence must include at least one
    user-perceivable artifact in the real environment — a UI screenshot, live
    output against the running service, a recorded interaction, or an
    equivalent. Pure unit-test passes alone are not sufficient; the spec must
    prove the feature is reachable from the user-facing surface. Configurable
    behavior introduced by the spec (e.g. new env vars, feature flags, default
    values) must be exercised under a realistic configuration, not just the
    safe default that disables the feature. This rule governs evidence
    *format* (what counts as proof) and applies independently of evidence
    *structure* requirements below.
29. **Sub-spec Intent reconciliation gate**: When a spec is decomposed into
    multiple sub-specs, the final sub-spec advancing to `done` must complete
    a reconciliation of the parent spec's Intent and Acceptance Criteria.
    Each parent-spec promise must be mapped to one of: (a) fully implemented
    with evidence reference, (b) explicitly out of scope with reason, (c)
    deferred to a named follow-up spec. The parent spec cannot be marked
    `done` until all promises are accounted for.
30. **Verify evidence must reference spec clauses**: For any spec advancing
    to `done`, the verify evidence must indicate which acceptance criteria
    it satisfies. For low-risk specs, a brief note in the evidence description
    is sufficient. For medium and high-risk specs, evidence must include a
    clause-by-clause mapping of each acceptance criterion to the evidence
    artifact that proves it. Evidence that does not reference a specific
    criterion must not be counted as acceptance evidence. This rule governs
    evidence *structure* (how evidence maps to criteria) and applies
    independently of the evidence format requirement in Rule 28. New specs
    should use explicit `AC1`, `AC2`, ... labels so the gate can report missing
    coverage precisely.
31. **Context freshness before major actions**: Before creating a new spec,
    generating a plan, or advancing a spec past `spec-ready`, the Agent must
    check whether the project context is stale. If context freshness is
    uncertain, the Agent must run `vibe context-refresh` or equivalent before
    proceeding. Stale context must not be used to make governance decisions.
32. **Dependencies must be satisfied before implementation**: A spec with
    declared dependencies cannot advance to `in-progress` until all
    dependency specs have reached at least `released` status. If a
    dependency is blocked or stalled, the Agent must surface it as a
    blocker rather than skipping or softening the dependency.
33. **Auto-record progress before context switch**: When the Agent detects
    that the user is switching from an `in-progress` spec to a different
    task (e.g. a new bug, a new requirement, or a different spec), the
    Agent must first record a progress evidence entry on the current spec
    summarizing what has been completed and what remains, before proceeding
    with the new task. The user does not need to explicitly request this.
34. **Git must be initialized**: When the Agent detects that the project
    directory is not a git repository, it must prompt the user and offer
    to initialize git before proceeding with any spec creation, advance,
    or evidence recording. Many governance features (clean worktree checks,
    commit-based evidence, changelog generation) depend on git being present.
35. **Bind the current project before project actions**: Before answering
    `next`, `status`, `acceptance`, `retrospective`, `advance`, or any action
    that reads or writes `.agents/`, the Agent must identify the current
    project root from the active repository or an explicit user path. It must
    not reuse a prior project's context merely because the same Skill or Agent
    session was used earlier. If the active root differs from the previous
    session context, switch silently and report the bound project; ask only
    when multiple candidate roots are plausible or no project root can be
    determined.
36. **Evidence command semantics must be unambiguous**: When recording evidence
    with a captured command, Vibe-owned options that change evidence semantics,
    such as `--purpose` and `--configured`, must appear before `--command`.
    If one is captured after `--command`, fail fast and explain the ordering
    instead of executing the project command and recording misleading failed
    evidence.
37. **Retrospective claims need evidence discipline**: A retrospective may
    discuss process, planning, or collaboration without reproduction proof.
    But any claim that a bug, failed behavior, or regression existed must cite
    evidence such as an evidence path, command output, log, screenshot, or
    recorded interaction; otherwise it must be clearly marked as an unverified
    historical note before it is used to seed new bug work.
38. **Spec creation must surface project guidance early**: Creating a spec must
    show the bound project guidance sources, including AGENTS.md presence and
    adopted project rules, then run an initial draft validation report. This
    gives the Agent immediate feedback in draft instead of waiting for a later
    status gate.
39. **Model effort is advisory and vendor-neutral**: `next` recommendations
    may include a suggested model effort tier (`lite`, `standard`, `strong`,
    or `review`) with a reason and upgrade condition. The Skill must not hard
    code vendor model names. Concrete model mappings belong in project-local
    or user-local configuration and must remain advisory; they are cost and
    workflow guidance, not status gates.
40. **External UI design tools are adapters, not acceptance sources**: When a
    UI spec uses output from a design tool, screenshot, generated prototype,
    or manual visual brief, the Agent must convert that source into a
    project-local UI Design Contract or UI Redesign Contract before treating
    it as implementation guidance. Screenshots, generated HTML, and tool
    exports may be references or evidence, but they are not sufficient as the
    only requirement or acceptance source. The contract must record source
    artifacts, model capability, layout, component mapping, states,
    accessibility expectations, numbered `UI-AC` clauses, and an evidence
    plan. For redesign work, it must also declare preserve/replace boundaries
    and behavior regression risks. Tool-specific setup and credentials remain
    project-local or user-local; the Skill core only governs contracts, gates,
    and evidence mapping. A design adapter name must not be inferred as a
    visual style, component system, animation model, icon strategy, or design
    system. Project-local rules and AGENTS.md constraints outrank adapter
    defaults or model assumptions; if the project forbids a visual pattern,
    the contract must record that constraint and the design source must be
    interpreted within it.
41. **New UI projects should be design-guided before first implementation**:
    When initializing or creating the first implementation spec for a new
    project that has a user-visible UI, the Agent must surface a design-first
    path before coding: clarify product intent, primary user flows, screen or
    route structure, key UI states, and whether a UI Design Contract should be
    created. If the user names a design adapter such as Open Design, Penpot,
    Figma, screenshot, or manual brief, follow Rule 40 and convert that source
    into the project-local contract. This is an early workflow prompt, not a
    universal hard gate: if the user explicitly chooses a code-first spike or
    the project is non-UI, proceed with the normal workflow and record the
    tradeoff in the spec or intent.
42. **UI design iteration must be versioned, not overwritten**: Any request to
    iterate, refine, adjust, redesign, or continue from an existing UI design
    must be treated as a versioned design revision even if the user does not
    explicitly say "do not overwrite." When a UI Design Contract, UI Redesign
    Contract, design source, or visual direction is revised after an earlier
    version exists, the Agent must preserve the prior version or archive it
    before writing the new one. Each version must have a stable version ID
    such as `v1`, `v2`, or a project-defined equivalent, and the project must
    retain enough prior contract/source artifact history to roll back to a
    previous design version. The revised contract or amendment must record the
    baseline version, changed items, preserved items, abandoned items,
    rollback target, affected `UI-AC` or behavior acceptance criteria,
    implementation/spec impact, and updated evidence needs. If the design
    change affects a spec that is already planned, in progress, under review,
    or released, the Agent must use the normal requirement amendment or
    follow-up spec flow rather than silently changing design guidance.
43. **Plan checkbox sync is advisory on spec advance**: When a spec reaches
    `review`, `released`, or `done` while its linked plan checkbox progress
    appears stale, the Agent must surface a warning and prompt to sync the plan
    or record moved/deferred tasks. Plan progress is advisory visibility, not a
    hard acceptance gate.

## State Model

Normal states are:

```text
draft → spec-ready → in-progress → review → released → done
```

Risk profiles may skip `review` or `released`. Any active item may become
`blocked`, `cancelled`, or `superseded`. Requirement amendments reset the item
to `draft` and archive stale downstream artifacts.

Before advancing:

- Reject missing or cyclic dependencies.
- Reject stale plans, evidence, or reviews.
- For bug specs, require ordered `reproduction` and `fix-regression` evidence.
- Reject amended specs whose risk has not been reconfirmed.
- Require configured command fingerprints when commands exist.
- Require a structured review decision rather than manual conclusion edits.
- Require observation evidence before high-risk work becomes `done`.

## Project Boundary

`.agents/workflow.json` contains only generic governance configuration:

- role assignments
- low/medium/high gate profiles
- verification, release, and observation commands
- optional repository membership

`.agents/policy-sources.json` records where project instructions come from and
how explicit conflicts were resolved. It stores governance metadata, not copies
of business rules. Default precedence is external mandate, existing project
policy, project-local Agent rules, then Skill defaults.

`.agents/policy-differences.md` is the human-readable summary for onboarding an
existing project. It lists higher-precedence project sources that still need
confirmation, where each source should land, open explicit conflicts, and
previously-seen sources that have gone missing.

`.agents/policy-confirmations.md` is the editable follow-up draft for those
pending sources. It gives each source a suggested landing and a minimal
decision skeleton plus a candidate patch snippet so the user or Agent can
confirm authority, chosen landing, and whether an explicit conflict is needed.

Specs may record owner, risk, dependencies, and release group. Cross-project
support is visibility and release-readiness reporting only; it is not an atomic
multi-repository deployment system.

These local artifacts provide consistency, not tamper-proof attestation.
Projects needing hostile-user resistance or regulated audit guarantees must
store evidence in an external trusted system.

## Operating Guidance

Prefer `scripts/vibe.py` for common operations. Use specialized scripts only
when the dispatcher does not expose the operation.

Run `vibe.py boundary <project_root>` before accepting a Skill-level
improvement. Deterministic project contamination is blocking; heuristic
technical-detail findings require human review.

Use `vibe.py next <project_root>` when the user asks what to do next. It must
consider unresolved high-risk policy conflicts, dependency cycles, risk gates,
artifact freshness, configured command evidence, review state, release state,
and missing retros. Return one primary action rather than every possible future
step, but explain it with a short gate summary, why a later stage is not yet
chosen, and one reasonable fallback action.

Read [references/workflow-reference.md](references/workflow-reference.md) only
when you need exact command syntax, script selection, phase checklists, or
self-improvement procedures. Do not load it for ordinary conversational
guidance when the next action is already clear.

Read [references/user-guide.md](references/user-guide.md) when the user asks
what they can say to the Skill, forgets available triggers, or needs a quick
reference for natural-language commands.

Read [references/adapters/opendesign.md](references/adapters/opendesign.md)
when the user explicitly asks to use Open Design, asks how to set up Open
Design, or provides Open Design artifacts as a UI design source. Treat the file
as adapter usage guidance only; Rule 40 still governs project constraints,
contracts, gates, and evidence mapping.

Run `doctor` before resuming an old or migrated workflow. Use migration rather
than inventing missing project decisions. Keep the Skill baseline generic and
compact.

## Suite Architecture

This Skill is the **core** of a suite. Auxiliary Skills (e.g. `vibe-coding-reviewer`)
live as siblings in the same monorepo. The user installs the core once; the core
links each auxiliary on demand via `vibe.py install-auxiliary --all`. Auxiliaries
share the project's `.agents/` state and only contain thin wrappers plus
role-specific instructions — they never duplicate the core's logic or carry
business knowledge. Add a new auxiliary only when a role must be performed by a
separate identity in a fresh session; do not split a single workflow's steps
into multiple Skills.
