---
name: vibe-coding
description: Vibe Coding project-governance skill covering discovery through retirement. Every git commit must use vibe commit (Rule 53 — mandatory review + verify gate). Use when the user describes an idea, change, defect, refactor, delivery problem, or project status question and Codex should translate it into the appropriate workflow; initialize or onboard projects; create and validate intents, designs, specs, plans, prompts, reviews, evidence, releases, changelogs, and retros; enforce risk-, role-, dependency-, Git-, and version-aware gates; migrate workflow schemas; diagnose integrity; summarize multiple projects; or evolve project-local guidance without adding project-specific knowledge to the skill.
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

<!-- ENFORCE: id=R1, hook=agent_end, action=check_gates, message=确保所有 gate 通过后才确认完成 -->
1. Treat Agent output as a proposal until required gates pass.
2. Bind plans, prompts, evidence, and reviews to the requirement version,
   durable project policy, and relevant source snapshot.
3. Ignore mutable workflow status and role assignments when computing
   requirement/policy freshness; they must not cause false invalidation.
<!-- ENFORCE: id=R4, hook=tool_call, tool=bash, match=vibe(?:\.py)?\s+(verify|evidence), action=block_without_verify, message=必须运行 workflow.json 配置的 verify 命令，没跑不能 record evidence -->
4. Execute configured project commands for mechanical checks. A written claim
   cannot replace configured command evidence.
<!-- ENFORCE: id=R5, hook=tool_call, tool=bash, match=vibe(?:\.py)?\s+next.*review, action=block_self_review, message=review 必须与 builder 不同身份，禁止 self-review -->

<!-- ENFORCE: id=R5b, hook=tool_call, tool=bash, match=vibe(?:\.py)?\s+next.*review, action=block_self_review_session, message=reviewer 必须是不同 session 或 sub-agent，禁止同一 session self-review -->

<!-- ENFORCE: id=R5d, hook=tool_call, tool=bash, match=vibe(?:\.py)?\s+(advance.*review|commit.*--reviewed), action=block_same_session_review, message=review 必须用独立 session，推荐 pi --print --no-session 或 codex exec 启动 reviewer，禁止同一 session self-review -->

    5b. **Review session separation (hard gate)**: When advancing
    to review, the reviewer MUST be a different session or
    sub-agent from the builder. In Pi, the current session ID
    is detected from `PI_SESSION_FILE` / `PI_SESSION_ID`. If
    the last builder actor equals the current session, the
    advance is blocked. Non-Pi agents without session context
    are skipped with a warning (not blocked). To bypass in
    solo-session emergencies, use `--role override_approver`
    with `--future-session` (R67).

    5d. **Review must use independent session (hard gate)**:
    When executing `vibe advance review` or `vibe commit
    --reviewed`, the current session is checked against the
    builder session. If they match, the operation is blocked
    with the message: "Review 必须用独立 session。推荐用
    `pi --print --no-session` 或 `codex exec` 启动独立
    reviewer session。" This gate enforces the principle that
    the implementer cannot review their own code. Projects
    may configure `workflow.json.review.independent_session:
    false` to downgrade to advisory (warning only).

5. Validate actor and declared role. Separated roles (reviewer, releaser,
   observer) must use a different identity from the builder, and the spec's
   risk level determines which transitions enforce this. The set of risk
   levels that require identity separation is configurable per project via
   `workflow.json.review_separation.required_for` and defaults to `["high"]`
   so existing projects keep their current behaviour. New projects and
   projects that opt in can add `medium` (and, less commonly, `low`) to that
   list to require an independent reviewer on every review transition. The
   reviewer does not have to be a separate human; an independent sub-agent
   or a separate session of the same Agent qualifies, as long as the
   reviewer identity recorded in the review document differs from the
   builder identity recorded in the activity log. The Skill never assumes
   a specific sub-agent mechanism (Task tool, helper Skill, fresh session)
   — the project / Agent runtime picks whatever works in its environment;
   what matters is that the recorded identities are different. The advance
   gate refuses a transition when separation is required and not present.

   **Single-actor escape hatch (`--role override_approver --reason "..."`)**
   applies only when the project genuinely has no second human identity
   available. All three conditions must hold: (a) the role is exactly
   `override_approver` (explicit intent, not a typo for builder/reviewer);
   (b) the supplied `--reason` is non-empty so the audit trail survives;
   (c) the supplied actor equals `workflow.roles.override_approver` so the
   override cannot be forged by any identity that is not the configured
   approver. The other review-quality checks (verify evidence, snapshot,
   clean worktree, plan digest) still run — this is a narrower escape than
   `--force`, which skips every gate.

   **Discovery surfaces** so users do not have to read this rule first:
   (i) `vibe advance --help` epilog prints the bypass template with all
   three conditions; (ii) when the advance gate rejects a transition for
   same-identity separation, the error block lists the escape-hatch
   command with copy-paste-ready `--actor` / `--role` / `--reason`
   placeholders and the three preconditions. This mirrors the e6d40ed
   "discovery-by-help-epilog" pattern so the upgrade is visible without a
   rule lookup. Prefer the helper Skills (`vibe-coding-reviewer` /
   `vibe-coding-debugger` in a fresh session) whenever a second identity
   is reachable; reserve the override for solo work where no second
   session is feasible. `--force` remains the last resort for emergencies
   and is logged with `actor` + `role = override_approver` + `--reason`.
6. Require actor, `override_approver` role, and reason for every forced
   transition.
7. Archive replaced or superseded evidence and downstream artifacts. Stale
    `.agents/` artifacts that no longer participate in any active spec are
    surfaced by `doctor` and `next` but are only moved by an explicit
    `vibe archive-stale` invocation; the Skill never archives files silently.
8. Redact common credential-shaped values before persisting command output.
9. Keep retrospective learning project-local. Add only evidence-backed rules,
   mark them proposed until adopted, and prune stale guidance.
<!-- ENFORCE: id=R10, hook=tool_call, tool=bash, match=vibe(?:\.py)?\s+evidence.*verify passed, action=block_incomplete_bug_evidence, message=bug fix 必须有 reproduction + fix-regression 双向证据，缺一不可 -->
10. For bug fixes: require evidence that the bug reproduced before the fix and
    no longer reproduces after. When a bug is a regression from a prior change,
    mark the regression source; review the original spec's retro for root causes.
11. When a change can affect existing behavior, require regression coverage or
    an explicit equivalent verification path. Prefer adding the test with the
    fix rather than deferring validation to a later cleanup.
12. **Composed-path verification for fallback and cross-component flows**: When a
    flow contains multi-step fallback or degradation paths, or when validation
    spans multiple components or boundaries, per-function or per-level checks
    are necessary but not sufficient. The Agent must additionally verify a
    composed path:

    - For each fallback or degradation level: confirm it works independently,
      then confirm that failure of an upstream level actually routes execution
      to the intended downstream level, and that the terminal fallback remains
      usable when every higher level fails.
    - For each cross-component handoff (user choice, frontend branch, backend
      endpoint, adapter, fallback target): confirm the end-to-end path
      resolves the same request through every component involved, and that
      each critical handoff preserves the intended semantics, ordering, and
      authorization state.
    - For each multi-process link in the architecture (a reverse proxy, ingress,
      sidecar, message broker, or any role whose job is to forward traffic to an
      upstream process): plan the degradation path at spec-ready, not at verify
      time. The forwarder must surface a structured error (an HTTP 5xx with a
      JSON body whose `error` field carries a code and a message is the
      recommended shape) when the upstream is unreachable, instead of the
      forwarder tool's default 5xx + text/plain. Front-end error handling must
      distinguish "network / process unreachable" from "HTTP business error" so
      the user sees a domain-specific message, not the raw status code or the
      forwarder tool's default text. After the upstream recovers, the retry
      path must succeed immediately, without being blocked by stale
      front-end caches, CDN caches, or service workers. The Skill never
      assumes a specific forwarder implementation (dev-server proxy, ingress
      controller, service mesh, cloud load balancer), a specific error-code
      vocabulary, or a specific process-isolation mechanism (container, PID
      namespace, sidecar pattern); the project decides all three. The three
      states to verify follow the Rule 13 pattern: valid (upstream reachable
      and returning the expected response), degraded (upstream unreachable
      and the forwarder returning a structured error the front-end can
      render), and recovered (upstream back online and retry succeeding).
13. **Time-sensitive state requires three-state verification**: When behavior
    depends on time-sensitive or freshness-sensitive state such as cache TTL,
    token expiry, propagation delay, or refresh windows, verify at least three
    states: valid, expired or stale, and recovered after refresh or
    re-resolution.
14. *(Intentionally removed — merged into Rule 13 during re-organisation;
    the three-state verification pattern covers the prior guidance.)*
15. When a spec touches topics covered by Rule 12 (composed-path verification for
    fallback or cross-component flows) or Rule 13 (time-sensitive or
    freshness-sensitive state), the Agent must check whether the project's
    testing rules already define the verification method for those scenarios.
    The check fires at the draft → spec-ready transition, not at verify time,
    so missing testing rules are surfaced when the spec is cheapest to revise.
    If the relevant testing rule is still unspecified at either gate, the
    Agent must pause and either record the project-local rule or explicitly
    surface the missing rule as a blocker. The verify gate re-checks the same
    condition as a second-line defence, not as the first discovery point. In
    addition, when the project's `workflow.json` declares
    `risk_required_rules[<risk>]` (a list of rule stems that the project
    requires for specs of that risk), the spec-ready gate refuses the
    transition unless each declared stem exists as an adopted project rule
    under `.agents/rules/`. The Skill never assumes a specific rule filename
    such as `security.md`; the project's declared stems are the source of
    truth, so a project can require `["security"]`, `["auth", "pii"]`, or
    any other stem that matches its governance model.
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
<!-- ENFORCE: id=R22, hook=tool_call, tool=bash, match=vibe(?:\.py)?\s+next, action=block_gate_violation, message=gate 条件不满足不能推进，先修复 gate 问题 -->
22. **Stage-transition gate**: Before advancing any spec's status, the Agent must
    run `vibe next` (or equivalent check) to confirm all gates for the target
    status are satisfied. After advancing, the Agent must run `vibe status` (or
    equivalent) to report the updated state. No status transition may happen
    silently without a preceding gate check and a following status report. When
    `vibe evidence <spec> verify passed` records a passing verification, the
    CLI prints a compact next-action hint summarising the spec's risk profile
    and remaining gates (review / release / observe). The hint is read-only
    guidance, never an implicit advance — review and observation gates must
    still be triggered explicitly. Before `vibe advance` runs the hard gate
    for the target status, the CLI prints a soft action checklist
    (missing evidence, high-risk reviewer-separation, dirty worktree, stale
    plan digest) and emits a `<!-- vibe:advance_checklist: ... -->` marker.
    The checklist is advisory only — the hard gate is the source of truth.
    Use `vibe advance --no-checklist` to suppress the checklist for
    emergencies; this is the same escape-hatch family as `--no-verify` and
    `--quick`.
23. **One active writer per spec**: Use one active writer per spec.
    Parallelize through separate specs or worktrees instead of adding
    distributed locking to this Skill.
24. **Inventory policy sources before proposing changes**: On existing
    projects, inventory policy sources before proposing changes. Existing
    project rules outrank Skill defaults. Do not infer semantic conflicts
    from keywords; record conflicts explicitly with sources, scope, severity,
    and resolution. Unresolved high-risk conflicts block affected specs from
    becoming `spec-ready`.
25. **Retrospectives must name the dominant failure mode**: Retrospective
    writeups should name the dominant failure mode in a compact, reusable way
    before listing fixes. Prefer the shared failure taxonomy when it fits so
    that later `self_analyze` runs can aggregate patterns across multiple
    retros.
<!-- ENFORCE: id=R25, hook=tool_call, tool=bash, match=vibe(?:\.py)?\s+retro, action=check_failure_labels, message=retro 必须引用 failure mode label，不能只写现象 -->
    25.1 **Failure mode labels are advisory triggers, not recovery playbooks**:
        When a retro names a shared-failure-mode label from the taxonomy
        (single-point verified / composed-path missing, steady-state
        verified / time-state missing, happy-path verified / degradation-
        path missing, component capability exists / routing wrong, rule
        exists but not bound to a gate, evidence exists but does not
        prove the claimed behavior), `vibe doctor` and `vibe next` may
        surface a corresponding recovery hint — but only when the project
        has explicitly adopted a project-local rule that addresses the
        label (Rule 18). The Skill never invents recovery playbooks from
        labels alone: that would cross the project/governance boundary
        (Rule 20) and would also leak project-specific knowledge across
        projects (Rule 9). Unlabeled failure modes are fine: state the
        mismatch explicitly instead of forcing a category, per the
        existing Rule 25 guidance.
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
    safe default that disables the feature. For acceptance criteria whose
    verb is "show", "display", "render", "include", "list", "expose", "呈现",
    "展示", "显示", "包含" or similar UI-presentation verbs, the user-perceivable
    evidence must be a UI-layer artifact — a real screenshot of the rendered
    surface, a Live HTTP response carrying the actual rendered HTML/DOM, a
    frontend component test that asserts what is visible, or an equivalent
    recording of the user-facing surface. A passing backend API test alone is
    never sufficient evidence for a UI-presentation AC, even when the API
    happens to return the data being shown; the AC promises what the user
    sees, not what the database contains. Specs that mix a presentation AC
    with an action AC in the same criterion must split them at spec-ready or
    verification time so each side carries its own evidence. This rule governs
    evidence *format* (what counts as proof) and applies independently of
    evidence *structure* requirements below.
    28.3 **Evidence must be re-runnable**: Beyond the per-AC reference and the
    fix-state anchor (Rule 25 advisory), the evidence artifact should include
    a command the reviewer can re-execute to reproduce the result. "Ran
    pytest" without the actual command, working directory, fixture, and expected
    output format is not re-runnable; the harness, not the agent, owns the
    verification loop (Voyager, SWE-bench Verified: external deterministic
    verification, not agent self-claim). When `record_evidence` accepts a
    `--command` argument the command is already captured automatically; for
    hand-written evidence that names a test or run without capturing the
    command, surface a non-blocking advisory reminding the author to attach
    the actual command line so a reviewer can reproduce the result. The
    advisory follows Rule 39 (default behaviour, opt-out).
28b. **Mock tests do not prove real network behavior**: When a spec
    modifies network request code (httpx, requests, aiohttp, urllib, fetch,
    or any HTTP client), the corresponding test files MUST include at least
    one test that exercises the REAL network behavior, not just mocks. Mock
    tests verify that the mock returns what you expect — they do NOT verify
    that the real API behaves the same way. Observed failure: a security fix
    for `_safe_request` had 1687 mock tests passing, but the real network
    call triggered TooManyRedirects because the mock never exercised the
    redirect chain. Enforcement: advisory only. `vibe commit` prints a
    Rule 28b advisory when the diff modifies network code and the test files
    only contain mock patterns (patch/Mock/MonkeyMock) without any
    real-network markers (@pytest.mark.integration, live_test, skipif
    network). Complements Rule 28: Rule 28 says "unit tests aren't enough",
    Rule 28b says "mock tests specifically don't prove network behavior".

29. **Sub-spec Intent reconciliation gate**: When a spec is decomposed into
    multiple sub-specs, the final sub-spec advancing to `done` must complete
    a reconciliation of the parent spec's Intent and Acceptance Criteria.
    Each parent-spec promise must be mapped to one of: (a) fully implemented
    with evidence reference, (b) explicitly out of scope with reason, (c)
    deferred to a named follow-up spec. The parent spec cannot be marked
    `done` until all promises are accounted for.
<!-- ENFORCE: id=R30, hook=tool_call, tool=bash, match=vibe(?:\.py)?\s+evidence.*verify passed, action=check_per_ac, message=verify evidence 必须包含 per-AC 映射，不能只写总结 -->
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
48. *(Intentionally removed — merged into Rule 39 during re-organisation.)*
49. *(Intentionally removed — merged into Rule 39 during re-organisation.)*
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

    Implementation: `scripts/create_design.py` lays down a two-track layout
    for every design. The current pointer lives at
    `.agents/designs/<name>.md` and carries frontmatter
    `当前版本: vN | 历史版本: v1,v2,...,v{N-1}` plus a
    `<!-- vibe:design_version_pointer: current=vN history=... -->` marker.
    Each iteration writes a new `.agents/designs/<name>.versions/v{N+1}.md`,
    archives the prior pointer content as `vN`, and refreshes the pointer
    frontmatter. Rollback copies `<name>.versions/vN.md` over the pointer
    and rewrites the version fields; archives are kept. Legacy flat
    `<name>.md` files (no `当前版本:` line) are auto-migrated to v1 on the
    first iteration. The Agent must never `git rm` or overwrite a version
    file without writing a follow-up retro; the same Rule 53 commit-review
    discipline applies to design-version commits.
43. **Plan checkbox sync is advisory on spec advance**: When a spec reaches
    `review`, `released`, or `done` while its linked plan checkbox progress
    appears stale, the Agent must surface a warning and prompt to sync the plan
    or record moved/deferred tasks. Plan progress is advisory visibility, not a
    hard acceptance gate.
44. **Write specs must surface read-path impact**: When a spec introduces a write
    operation, a state mutation, a schema change, a new storage location, or any
    change that can be observed by an existing read path, the spec's scope
    section must list every read path that may be affected, or explicitly mark
    "no read path affected" with a one-line reason. The Agent must not leave
    this section empty or skip it. The list exists to make the cross-component
    handoff visible at spec-ready time so Rule 12's composed-path verification
    can be planned for, not discovered at verify. Whether a read path is
    actually affected is a project-specific decision; this rule only requires
    the spec to surface the consideration explicitly rather than rely on later
    verification to catch an implicit impact.
45. **Stale artifact archive is explicit, not automatic**: `doctor` and `next`
    surface stale `.agents/` artifacts (evidence for `released`/`done` specs,
    unreferenced rules, untouched `cancelled`/`superseded` specs) but never
    move them. The threshold for each kind is configurable in the project's
    `workflow.json` under `archive.thresholds_days`; the Skill default is
    conservative (evidence 90 days, rule unreferenced 180 days, spec untouched
    365 days). The Agent runs `vibe archive-stale <project_root>` to preview
    and `vibe archive-stale <project_root> --apply` to execute. The script
    never recurses into `.agents/archive/` and never deletes anything; archived
    artifacts land in `.agents/archive/<UTC-timestamp>/<original-relative-path>`
    with a `manifest.json` describing each move. This rule keeps archive a
    visible, reversible action: no implicit project-state mutation.
46. **Stage-stall is observable, not blocking**: When a spec stays in the same
    stage longer than its risk SLA (default: low 72h, medium 24h, high 8h),
    `status` and `next` print a low-priority advisory listing the spec, current
    stage, and elapsed hours. The Skill reads the entered-at timestamp from
    `.agents/activity.md` (auto-written by `set_status` whenever status changes);
    specs without an activity entry are skipped because the Skill cannot reason
    about duration without a timestamp. The per-risk threshold is configurable
    in `workflow.json` under `stage_stall_sla`. The advisory never blocks
    advancement — `vibe advance` still runs as long as its own gates pass; the
    hint exists so the Agent notices a spec that has been stuck and can decide
    whether to advance, amend, or cancel it.

<!-- ENFORCE: id=R47, hook=tool_call, tool=bash, match=vibe amend-spec, action=block_stale_prompt_version, message=amend 后必须 bump Prompt version，旧版本不能 commit -->
47. **Spec frontmatter must declare a Prompt version**: Every spec carries a
    `> Prompt version: N` line in its frontmatter (alongside `> 状态:`, `> 风险:`,
    etc.). `create_spec.py` writes `1` at creation; `spec_amend.py` bumps to
    `N+1` whenever the spec is amended. The version tracks the agent-facing
    prompt and plan context: when the underlying requirement changes, the
    version tracks that the agent's instructions are now anchored to a new
    requirement version. `doctor` emits a non-blocking advisory when a spec
    file is missing the line, and a second advisory when a spec has been
    amended in git history but the version did not bump — both are advisory
    only (Rule 39); the rule prevents silent prompt drift across amendments
    (12-Factor #1: own your prompts).

50. **Vibe output carries machine-readable markers for key decisions**: The
    terminal output of `vibe status`, `vibe next`, `vibe doctor`, and
    `vibe advance` wraps each material decision in an HTML comment marker of
    the form `<!-- vibe:<key>: <value> -->`. Recognized keys: `next_action`
    (the recommendation emitted by `next`/`status`), `next_target` (the
    spec the recommendation targets, when applicable), `status_summary`
    (spec count and recommendation summary at the end of `status`),
    `doctor_health` (`clean` or `issues` plus counts at the end of `doctor`),
    and `gate_verdict` (`pass`, `forced`, or `fail` plus the spec name and
    transition at the end of `advance`). Markers are backwards compatible
    because they are HTML comments — humans ignore them, and any consumer
    that does not know about Rule 50 sees the same natural-language output
    as before. Agents that want to parse vibe output should grep the markers
    before falling back to natural-language parsing (12-Factor #11:
    structured outputs, applied at the harness boundary rather than the
    agent-internal boundary).

51. **Bug fix scope declaration**: Any spec with `> 类型: bug` must carry
    a `## 修复范围 (Fix Scope)` section. The section is structured into
    three sub-parts and exists to defeat the recurring "fix only covered
    one of N instances" failure mode (12-Factor #4: small steps with
    external memory; the section is the memory, the spec is the step).

    1. **已修复位置** — every location the fix actually touches, with
       `path:line` and a one-line description of what changed. The list
       is positive: things the agent did, with evidence.
    2. **故意不改的相邻位置** — every adjacent location that looks like
       the same bug but was deliberately left alone, with a one-line
       reason. The list is negative-space: the agent must walk the
       candidate set, not just the chosen set, and must justify each
       non-fix. This is the half that catches "found but misjudged"
       failures like adding `require_login` to an OAuth entry point
       (the agent saw the endpoint but classified it as "needs auth"
       instead of "is the auth mechanism").
    3. **判断依据** — the standard the agent used to decide which
       locations belong to this bug (shared root cause / shared API /
       shared branch / shared auth context / etc.). Recording the
       standard lets the next agent or reviewer see whether the
       standard was applied consistently.

    `create_spec.py` renders the section as a placeholder for type=bug
    specs only (other spec types do not get the section, so the rule
    is non-intrusive). `doctor` emits a non-blocking advisory when a
    type=bug spec is missing the section. Verify must reference the
    section: for each location listed under 已修复位置, the evidence
    must show the bug behavior is gone; missing-evidence locations
    block `advance` to `done` only at the rule-binding point
    configured in `workflow.json.fix_blast_radius.required_for`
    (default advisory, opt up to `["high"]` or `["medium", "high"]`).
    When the rule fires retroactively — a fix shipped, then a
    regression appears in an unlisted adjacent location — the failure
    is logged as `single-fix verified, blast-radius missing` so
    `self_analyze` and Rule 25.1 surface it next cycle.

52. **Skill version drift is observable, not silently tolerated**: The
    Skill ships a `VERSION` file containing the git short hash of the
    installed commit. `init_project.py` (and `onboard_project.py`)
    write that value to `.agents/.skill-version` when a project is
    initialised or onboarded. `vibe doctor` reads both files on every
    run; when the project-recorded value differs from the installed
    value, doctor emits a single non-blocking warning of the form
    `Skill version drift: project records '<old>', installed Skill is
    '<new>' (Rule 52). Reload the Skill in the active session or open a
    new one to pick up the new rules.`

    The rule is purely advisory. The project itself is unaffected by
    Skill version drift; only the agent's loaded rule set may be
    behind, which means the agent may follow older governance and
    miss new advisories (e.g. a project whose agent has not picked up
    Rule 51 will not declare Fix Scope sections on new bug specs).
    The advisory exists so this gap is visible without the user
    having to remember which project agents were active when the
    last Skill update shipped. Pre-Rule-52 projects (no
    `.skill-version` file) are silently treated as 'unknown' and do
    not back-warn; they get a version recorded on the next init or
    onboard. Missing `VERSION` in the installed Skill (dev checkout,
    broken symlink) is also treated as 'unknown' and does not
    false-positive. The Skill deliberately does not attempt to force
    a client-side Skill reload: that capability is owned by the agent
    runtime (Codex / Trae / Claude Code) and is not exposed today;
    Rule 52 narrows the gap from "blind" to "visible" within the
    Skill's authority.

    **Rule 52.1 — Maintainer-side VERSION drift check**: `vibe
    doctor` and `vibe upgrade` MUST also detect the inverse
    failure mode: the Skill maintainer forgot to bump `VERSION` in
    the latest commit, leaving downstream projects' version-drift
    checks blind to the new rules. The check compares the
    working-tree `VERSION` string against the Skill's git `HEAD`
    short hash (VERSION convention: starts with `<7-char-hash>-`).
    If they do not match, a warning is emitted. This was added
    after observing the maintainer ship 9 commits without bumping
    `VERSION`, causing every downstream `vibe doctor` to falsely
    report "version is up to date".

"version is up to date".

    **Rule 52.2 — `vibe version-bump` Skill self-maintenance command**:
    Maintainers MUST run `python3 scripts/vibe.py version-bump` (or
    `vibe version-bump` from the Skill repo root) instead of hand-typing
    `chore(skill): bump VERSION to <hash>-<slug>` commits. The command
    computes `<7-char-head-hash>` from `git rev-parse --short HEAD` and
    the slug from the most recent non-bump commit's subject, eliminating
    the recurring failure mode where maintainers wrote the **previous**
    feat commit's hash into VERSION. The command is idempotent: it
    no-ops when HEAD is already a `chore(skill): bump VERSION` commit
    and the tree is clean (the "ran bump twice in a row" case). It
    always lands a single commit with subject `chore(skill): bump VERSION`
    (no hash in the subject — subject ↔ SHA is a chicken-and-egg loop
    better left unsolved; VERSION content is the drift source of truth).

<!-- ENFORCE: id=R53, hook=tool_call, tool=bash, match=git commit(?!.*vibe commit), action=block, message=请使用 vibe commit，禁止 raw git commit -->

    53. **Pre-commit verification gate**: Every `git commit` must be wrapped
    in the `vibe commit` wrapper, not invoked as raw `git commit`.
    The wrapper enforces three discipline steps that agents otherwise
    skip:

    1. **Review** — show the full `git diff` (not just `--stat`) so
       the Agent can inspect actual code changes. The Agent must
       review the diff content for unintended modifications, scope
       creep, or regressions. If issues are found, the Agent must
       fix them before committing — the review is not a passive
       display, it is an active inspection gate. The diff must also
       be checked against the spec's `## 涉及范围` (Rule 44 spirit:
       scope discipline). A `--stat` summary is shown alongside the
       full diff for quick orientation, but the stat alone is
       insufficient — file names and line counts cannot reveal
       logic errors, accidental deletions, or wrong variable names.
       The commit process enforces a mandatory two-step review:
       (1) `vibe commit` shows the full diff and then stops (exit 5),
       forcing the Agent to read the diff before proceeding. As a
       side effect, step 1 writes a marker to
       `.agents/.vibe-review-pending` (auto-added to `.gitignore`).
       (2) `vibe commit --reviewed` runs verify and commits, but only
       when the step-1 marker exists in the target project. If the
       marker is missing (because the Agent skipped step 1, or ran
       step 1 in a different project), `--reviewed` is rejected with
       exit 6. The marker is removed after a successful commit, so
       the next commit must repeat step 1.

       The Agent must not combine these into a single step —
       `vibe commit --reviewed` without a prior review step is a
       policy violation. This enforced two-step design prevents the
       observed failure mode where the Agent adds `--reviewed`
       upfront and never actually reads the diff. Note: `--quick`
       skips the gate entirely (no marker required) for docs-only /
       low-risk commits; `--no-verify` skips both gates for
       emergencies.
       
       Before the review gate, the wrapper runs an advisory
       evidence-grep pass that highlights sensitive patterns in the
       diff (emit/write/INSERT/UPDATE/DELETE/fetch POST/json.dumps).
       These patterns commonly hide "test passes but data semantics
       are wrong" bugs. The grep is non-blocking — it just prints
       a risk summary so the Agent knows where to focus attention
       during review.
    2. **Verify** — run every command listed in
       `workflow.json.commands.verify`. If any command exits non-zero,
       the commit is aborted before a single byte reaches the project
       history. The verify phase is the same one `vibe verify` and
       the spec-verify gate already use (Rule 22, Rule 28, Rule 30);
       the wrapper re-runs it at the commit moment because between
       spec-verify and commit, the agent may have touched other
       files, and the verify evidence the gate relied on may no
       longer match the worktree.

       **Fail-open protection**: If the verify phase itself crashes
       (e.g. regex bug in a verify command, misconfigured command),
       the wrapper catches the exception, prints a warning, and
       allows the commit to proceed with a `Verify-Crash: <ErrorType>`
       trailer. This prevents a broken verify configuration from
       blocking all commits — the commit still happens, but doctor
       can detect that the verify gate was bypassed due to an
       internal error.
    3. **Commit** — only if both pass, hand off to `git commit` with
       the user's argv unchanged.

    `--quick` escape hatch: for docs-only or low-risk chore commits,
    `vibe commit --quick` skips the review gate but still runs verify.
    The commit trailer becomes `Vibe-Commit: quick` so doctor can
    distinguish quick commits from normal ones. This is the honest
    escape hatch — it does not hide that the gate was skipped.

    **Rule 53b — `--quick` / `--no-verify` are for docs-only, not runtime code**:
    The `--quick` and `--no-verify` escape hatches must NOT be used for
    changes that affect runtime behavior (source code in `src/`, `app/`,
    or any file with a runtime extension: `.py`, `.js`, `.ts`, `.go`,
    `.rs`, `.java`, `.rb`, `.php`, `.c`, `.cpp`, `.swift`, `.kt`,
    `.sql`, etc.). These flags bypass the review gate and/or verify gate,
    which means regressions go undetected. Observed failure: 20/81 quick
    commits were business code (fix/feat), not docs — the flag was used as
    a general "gate is annoying" bypass rather than its intended docs-only
    purpose. A specific regression: `_safe_request` DNS pinning broke
    redirect chains for 4 days because the fix used `--quick` and the
    reviewer never inspected the diff.

    Enforcement: advisory only (no hard gate). When `--quick` or
    `--no-verify` is used with staged runtime files, the wrapper prints
    a `⚠️ Rule 53b advisory` reminding the agent to use the full
    two-step review flow. The agent MAY still proceed (for genuine
    emergencies), but MUST record the bypass reason in the retro (Rule 54).
    Test files (`tests/`, `test/`, `__tests__/`, `spec/`) are NOT
    runtime code — `--quick` is allowed for test-only changes since they
    don't change production behavior.
<!-- ENFORCE: id=R53b, hook=tool_call, tool=bash, match=vibe(?:\.py)?\s+commit.*(--quick|--no-verify), action=block_runtime_bypass, message=--quick/--no-verify forbidden on runtime code -->

    **Rule 53c — `--quick` disables both review lines of defense**:
    The vibe coding review architecture has two lines of defense:
    (1) agent self-review (`vibe commit` step 1 → step 2, same agent
    reads diff and writes review-summary), and (2) independent review
    (`vibe review`, sub-agent with separate identity). When `--quick`
    is used, defense (1) is skipped. Defense (2) is NOT auto-triggered
    — `vibe review` requires explicit invocation. The result: both
    defenses are down simultaneously, and the commit lands with zero
    review. After a `--quick` commit succeeds, the wrapper prints a
    `⚠️ Rule 53c advisory` reminding the agent to run `vibe review`
    for business code changes. This complements Rule 53b: 53b reduces
    misuse (only docs-only), 53c catches the leaks (remind to add
    independent review).

    **Rule 53d — gate bypass tracking with pending review marker**:
    When `--quick` or `--no-verify` commits succeed, the wrapper writes
    a `.agents/.vibe-pending-reviews.json` marker file (gitignored)
    recording the commit hash, bypass type, and files changed. The
    marker creates a persistent reminder chain:
    - `vibe next` and `vibe status` check the marker and display
      pending reviews at high priority, listing each bypassed commit.
    - `vibe doctor` also checks the marker as a routine inspection item.
    - `vibe review-decision` clears matching entries from the marker
      after a review is recorded, and deletes the file when empty.
    This creates a closed loop: bypass → marker → persistent reminder
    → review → clear. Complements 53b (reduce misuse) and 53c
    (immediate reminder): 53b reduces the entry, 53c fires once, 53d
    persists until the review is actually done.

    **Rule 53e — context-sensitive advisories triggered by staged file paths**:
    Soft constraints become effective when they meet the agent on the
    path the agent must walk (the commit gate). `vibe commit` step 1
    scans staged file paths and triggers context-sensitive advisories:
    - **Runtime code** (app/src/lib/backend + .py/.js/.ts/.go/etc.):
      reminds to restart the service and run a smoke test before commit.
    - **Security code** (safe/auth/security/middleware/ssl/tls):
      reminds to add at least 1 non-mock test (complements Rule 28b).
    Projects can extend these by adding markers in `.agents/rules/`
    files: `<!-- vibe:commit-advisory: pattern="regex" message="text" -->`.
    The Skill provides the framework and defaults; projects provide
    domain-specific rules. Advisory only, never blocks commit.

    Per-file-summary line-ref hard gate (2026-07-08, scheme B): after
    the per-file mention gate passes, `vibe commit --reviewed` runs a
    second scan that rejects the commit (exit 9) if any per-file
    conclusion in the summary lacks a line-number reference
    (`L25` / `line 25` / `:25`) or a backtick-wrapped code fragment.
    The gate defeats the failure mode where an Agent writes
    "file A: +12 lines added helper" from memory without ever
    re-reading the actual diff — the format passed the per-file
    mention check but the review substance is hollow. Failure marker:
    `<!-- vibe:commit_review_gate: missing_line_refs -->`. Bypass:
    `--quick` (skips the entire review gate, still runs verify) or
    `--no-verify` (skips review + verify). Acceptable signals:

    - `L25`, `L25-L30` — explicit line number
    - `line 25`, `line 25-30` — line-range reference
    - `:25` — diff-style position (matches what `git diff` shows)
    - `` `helper_name` `` — backtick-wrapped identifier or code fragment

    Suggested format: `<file>: L<line> <observation>; <file>: L<line> <observation>`

    Help-text template: the worked template (per-file + L<n> + backtick
    code fragment) lives in `commit.REVIEW_SUMMARY_TEMPLATE` and is
    surfaced via the commit subparser epilog, so `vibe commit --help`
    prints it at the end of the usage block (argparse
    RawDescriptionHelpFormatter). Doctor and project_status output the
    recovery steps when a commit is missing Vibe-Commit trailer:
    `git reset --soft HEAD~N` then redo the two-step `vibe commit`.
    Amending the message to add a trailer is forbidden — the SHA changes,
    invalidating the trailer hash.

    Failure modes the gate is designed to catch (all observed in
    real projects):

    - "Spec is `done`, tests pass, but I edited something else after
      the verify run and committed it without re-running tests."
    - "Diff is way larger than the spec's scope — the agent did
      drive-by edits that nobody reviewed."
    - "I added a regression test that I never actually ran."

    `vibe commit --no-verify` is provided as a documented escape
    hatch (e.g. for docs-only commits where the verify phase would
    be wasteful). Emergency is not a reason to skip review — if
    speed matters, the review should be faster (parallel prep), not
    absent. Every `--no-verify` usage must carry a reason via the
    `--no-verify "<reason>"` form and that reason must be
    acknowledged in the spec's retro. The escape hatch is
    intentionally an explicit flag, not a default behaviour, so
    casual use of `vibe commit` does not silently skip the gate. A
    user who wants strict enforcement can install a git pre-commit
    hook that runs `vibe commit --verify-only` (the Skill ships a
    one-liner install command); the hook then blocks raw `git
    commit` for everyone working in the project.

    A project that has not configured `workflow.json.commands.verify`
    cannot use `vibe commit` at all — the wrapper refuses with a
    clear message and the exact `workflow.json` snippet to add.
    This forces every Vibe Coding project to declare its verify
    command up front (Rule 4 spirit: configured commands over
    written claims), and means Rule 53 cannot accidentally regress
    to "trust the agent" mode.

    `--review-summary` (mandatory when using `--reviewed`): the second
    step of the two-step gate MUST include a short text describing
    what the Agent actually found while reading the diff. The wrapper
    rejects an empty summary with exit 7 and the marker
    `<!-- vibe:commit_review_gate: missing_summary -->`. A non-empty
    summary is written to the commit as a `Review-Summary: <text>`
    trailer and the success marker
    `<!-- vibe:commit_review_summary: <first 60 chars>... -->` is
    emitted. This makes "did the Agent actually read the diff?"
    observable in the git log — `git log --grep='^Review-Summary:'`
    shows the summaries and the absence of a trailer on a commit
    tells the reviewer that the gate was skipped (`--quick` /
    `--no-verify`) or that the summary was empty (which is now
    impossible). Failure to provide a summary is treated as
    equivalent to skipping the review.


54. **Doctor warnings must be acted on, not just displayed**: When
    `vibe doctor` or `vibe next`/`vibe status` surface warnings
    (stale context, missing rules, Skill version drift, stage-stall,
    missing retros, missing changelogs, proposed rules unreviewed),
    the Agent must not silently continue as if nothing was wrong.
    Each warning must be either resolved (by running the suggested
    command) or explicitly deferred with a reason recorded in the
    project. Ignoring a warning without acknowledgment is the same
    failure mode as Rule 53's original "show stat but don't review
    content" — the output exists but has no effect on behavior.
    The `vibe next` recommendation must account for unresolved
    warnings: if context is stale, recommend context-refresh first;
    if Skill has drifted, recommend upgrade first; if rules are
    unreviewed, recommend rule-status decision first.

55. **Review must inspect content, not just confirm existence**: When
    a review is performed (whether via `generate_review.py` or
    inline during `vibe commit`), the reviewer must inspect the
    actual code changes and reason about correctness, not just
    confirm that files exist or tests pass. A review that says
    "looks good" without referencing specific diff hunks, spec
    clauses, or acceptance criteria is not a valid review — it is
    the same failure mode as Rule 53's original "show stat but
    don't review content". The review conclusion must reference at
    least one specific observation from the diff or the spec.

56. **Adjacent-location protection is advisory**: When a bug spec's
    Fix Scope (Rule 51) lists "故意不改的相邻位置", the Agent should
    verify those locations were not accidentally affected — either by
    writing a protection test, or by explicitly declaring "no automated
    test protection, risk acknowledged" with a one-line reason.
    `vibe doctor` surfaces an advisory for adjacent locations that have
    neither a protection test nor an explicit risk acknowledgment. The
    advisory is not blocking; it exists because the "deliberately
    unchanged" declaration is hollow without evidence that it stayed
    unchanged, and this is the same "exists but unverified" failure
    mode that Rule 53 originally had with `--stat`.

57. **Read-path impact type must be annotated**: When a spec's scope
    section (Rule 44) lists read paths that may be affected, each path
    must be annotated with an impact type: `新增` (new field/endpoint/
    return value, no existing behavior changed), `修改` (changed
    semantics, format, or contract of an existing path), or `删除`
    (removed field/endpoint/return value). Paths annotated as `修改`
    or `删除` represent behavior changes — their verify evidence must
    include a before-vs-after comparison showing the actual behavior
    change. `vibe doctor` surfaces an advisory for read paths listed
    without an impact-type annotation. Unannotated paths default to
    `新增` only when the spec is `type=feature` and the path did not
    exist before; otherwise they require explicit annotation.

58. **Retro must record behavior changes and rollback plan**: When a
    spec changes existing behavior (read paths annotated as `修改` or
    `删除` per Rule 57), the retro must include: (1) a description of
    the behavior change (before vs after), (2) an assessment of who or
    what is affected, (3) the business decision for accepting the
    change, and (4) a rollback plan describing how to restore the
    previous behavior. `vibe doctor` surfaces an advisory for specs
    with `修改`/`删除` impact annotations whose retro is missing any
    of these four items. The assessment of impact (item 2) should use
    whatever evidence is available in the project — logs, queries,
    test data, or manual testing — but the rule does not mandate a
    specific tool or data source, as that is project-specific.

59. **Behavior-invisible constructor / dependency changes require call-site grep**: When a spec modifies an existing class `__init__` or dependency wiring in a way that is INVISIBLE to type checkers and IDEs (e.g. a previously-dormant parameter now flows through to a superclass; a default value flips behavior; a third-party client switches transport), the spec §涉及范围 MUST list every call site of the affected symbol in the project (file:line + status: `adapted` / `needs-adaptation` / `n/a` + reason). The review MUST run the same grep independently — a builder's claim of "I checked all call sites" is not acceptable evidence; the reviewer must show the grep command and its raw output. Any call site marked `needs-adaptation` that is outside the spec's Fix Scope → reject approve. Pure signature changes (add/remove/rename parameter, default value visible in signature) are NOT covered — type checkers catch those.

<!-- ENFORCE: id=R60, hook=agent_end, action=check_retro_items, message=retro action items 必须达到终端状态（active/deferred/superseded），不能留空 -->
60. **Retro action items must reach a terminal state**: When a retro identifies a gap and writes an action item, the item MUST progress to a terminal state before the next retro cycle closes: `[active: <rule-id>]` (promoted into `.agents/rules/` or a Skill-level rule with explicit cross-reference), `[deferred: <reason>]` (parked with explicit rationale, no spec-id dependency), or `[superseded: <other-id>]` (replaced by later work). Items persisting as `[ ]` across multiple retro cycles signal forgotten work; `vibe retro --audit-stale` lists them and `vibe next` surfaces them as advisory before any new work. Wall-clock deadlines are intentionally not used — project cadence varies (some ship 5 specs/day, some 1/week); counting retro cycles keeps the rule applicable at any pace while still surfacing true stagnation. "I'll handle it later" without an explicit `[deferred: ...]` state is forbidden.

61. **Multi-call-site gaps: grep is the source of truth for follow-up scope**: When a retro, spec, or review identifies a class / function / module referenced from more than one place in the project, the complete call-site list MUST be generated by grep at retro time — not inherited from any prior numbering scheme. Each call site gets one of four states: `active` (working correctly), `pending` (needs the fix), `latent` (currently passes but depends on behavior that the gap calls into question), or `n/a` (with reason). Follow-up scope = all `pending` + `latent` entries, NOT the originally-numbered subset. The `latent` state exists because "passes tests today" is not proof of safety when the underlying behavior is being changed. Forbid: following up only the originally-numbered entries without re-grepping; closing a multi-call-site gap based on partial coverage; treating "done" call sites as safe when their underlying behavior is being modified.

<!-- ENFORCE: id=R62, hook=tool_call, tool=bash, match=vibe(?:\.py)?\s+commit.*reviewed, action=block_unverified_call_sites, message=commit 前必须 grep 所有受影响调用点，没查不能 commit -->
62. **Call-site grep gate (Rule 59/61 enforcement)**: Rules 59 and 61 are advisory without enforcement — this rule binds them to hard gates. (a) **Spec-ready gate**: a spec with a `## 调用点 (Call Sites)` section that has no concrete call-site entries and no explicit N/A sentinel cannot advance to `spec-ready` (enforced via validate_spec Rule 59 warning blocking the transition). (b) **Commit verify gate**: projects MAY configure `commands.call_site_check` in `workflow.json` — if configured, `vibe commit` runs these commands after verify and rejects the commit on failure (exit 8). This is optional; projects that don't configure it are not affected. Example configuration: `{"commands": {"call_site_check": [["bash", "-c", "grep -rn 'parse_link(' backend/ | wc -l | grep -q 6"]]}}`. (c) **Retro gate**: `vibe retro --check-call-site-coverage` scans retros that mention call-site keywords and flags those missing a grep-generated call-site list with 4-state classification (active / pending / latent / n/a). This is advisory, not a hard gate — retros are reflective documents, not commit blockers. The commit review gate (reviewer independent grep) remains a text-level MUST under Rule 59; this rule does not add a mechanical enforcement for it because reliably parsing review content is unreliable.


63. **AGENTS.md phase-gates template is versioned and merge-safe**: The Skill ships a `templates/agents-phase-gates.md` template containing the `## 阶段强制规范（Phase Gates）` section with 9-phase hard gates (Discover → Done), per-phase mandatory checkpoints, allowed-skip conditions, and prohibited-skip conditions. When a project is initialised (`vibe init`) or onboarded (`vibe onboard`), the project's AGENTS.md is generated from this template. When the Skill updates the template, `vibe update-agents <project_root>` replaces the phase-gates section in the project's AGENTS.md while preserving all project-specific content (tech stack, architecture constraints, etc.). The section is versioned with a `<!-- vibe:phase-gates-version: <hash> -->` marker; `vibe context-refresh` checks this marker and auto-updates when drift is detected. Projects MAY declare overrides in a `## 阶段覆盖声明（Phase Gates Override）` section; during merge, project overrides take precedence over Skill defaults and the merged section annotates the override. The template must never contain project-specific knowledge; it is a governance skeleton only.

64. **`asyncio.create_task` MUST NOT call `.commit()` on a shared AsyncSession**:
    When a spec, plan, or fix introduces a `db.commit()` / `session.commit()` /
    `AsyncSession.commit()` call inside the body of `asyncio.create_task(<callable>)`,
    and the parent coroutine shares the same session / `AsyncSessionLocal` /
    `session_factory` instance, the commit races with the parent and crashes
    with `IllegalStateChangeError: Method 'commit()' can't be called here;
    method 'commit()' is already in progress`. The fire-and-forget task's
    exception handler silently swallows the error, so the parent transaction
    rolls back without the agent noticing. `vibe commit` runs an advisory AST
    scan over the staged `.py` files (Rule 64-style — see
    `scripts/code_pattern_gate.py`) and emits warnings before commit. The
    scan is **advisory, not blocking**: the fix is `asyncio.Lock`, a fresh
    `AsyncSession` inside the task, or moving the commit to the parent
    coroutine. Escape hatch: `vibe commit --no-async-gate` for actor-model
    projects with independent session factories, one-shot background writes
    via `async_sessionmaker()`, or any other pattern that has already been
    audited. The scan uses `ast` (not regex) so docstrings, comments, and
    string literals are not falsely matched; it walks every
    `asyncio.create_task(...)` call whose first positional argument is a
    Lambda / FunctionDef / AsyncFunctionDef and whose body references
    `session` / `db` / `AsyncSession` / `Session` / `_session` / `_db` /
    `conn` / `connection`. Pure signature changes (renaming, parameter
    ordering, return-type widening) are NOT covered — type checkers catch
    those.

65. **Bug inbox is an opt-in append-only ledger**: Projects MAY enable a `.agents/bug-inbox.md` ledger by setting `workflow.json.bugs.inbox = true` (default: `false`). When enabled, `vibe init` generates `.agents/bug-inbox.md` from `templates/bug-inbox.md` with a fresh append-only scaffold (header + risk-level matrix aligned with R10 + verification note format + closure rules + sync rules + speed-lookup commands). The inbox is the entry point for bugs that originate from scans, retro discoveries, or external reports; hotfixes (user-reported mid-session) MAY bypass the ledger but must reference the bug description in the commit message. Every inbox bug line MUST follow the format `- [ ] <risk>: <description> — <path:line> (<date>)` with at least one indented verification note (`- 验证 (date, actor): ✅/❌/⚠️ + concrete conclusion`). Closure flips `[ ]` to `[x]` and appends a `关闭 (date, actor): ✅/❌ <reason> — <commit-sha> (<spec-name> done)` line; rows are never deleted (append-only preserves audit trail). Two drift-detection surfaces enforce sync discipline without hard-blocking: (a) `vibe commit` emits an advisory when the commit message references `fix-<name>` (matches both `fix-name` and conventional-commits `fix(name)`) but the inbox still has an open `- [ ]` row for the same name — soft warning (仿 R53 soft_claim pattern, 不阻塞 commit); (b) `vibe doctor` emits a warning when any spec with status `done` or `released` has an open inbox row referencing its name — surfaces drift retroactively across past commits. Both run only when `workflow.json.bugs.inbox = true` so projects without inbox pay no cost. Projects that already have a `.agents/bug-inbox.md` (e.g. ones that adopted the pattern before this rule) are NOT overwritten by `vibe init`; their content is preserved verbatim so the ledger keeps continuity.
<!-- ENFORCE: id=R66, hook=before_agent_start, action=inject_prompt, message=会话恢复后必须先运行 vibe status + vibe next（两步都必须执行，不能只跑 status 跳过 next） -->

<!-- ENFORCE: id=R67, hook=tool_call, tool=bash, match=vibe(?:\.py)?\s+advance.*override_approver, action=block_self_override, message=override_approver 必须指定非当前 session 的 actor，self-override 禁止 -->

    67. **Override-approver session separation**: When using
    `--role override_approver` to bypass the review_separation gate,
    the `--actor` value MUST differ from the current session ID.
    Self-override (same session as builder) defeats the purpose of
    review independence. In Pi sessions, the current session ID is
    detected from `PI_SESSION_FILE` or `PI_SESSION_ID` environment
    variables. If no session context is available, the gate is
    skipped with a warning (not blocked). Other agents (Codex,
    Claude, Cursor) that lack session IDs are unaffected - the gate
    only enforces when session context is available.

<!-- ENFORCE: id=R68, hook=tool_call, tool=write, action=block_spec_state, message=写业务代码前 spec 必须 in-progress，禁止跳过流程直接写代码 -->
<!-- ENFORCE: id=R68e, hook=tool_call, tool=edit, action=block_spec_state, message=写业务代码前 spec 必须 in-progress，禁止跳过流程直接写代码 -->

<!-- ENFORCE: id=R28b, hook=tool_call, tool=bash, match=vibe(?:\.py)?\s+advance.*done, action=block_no_user_evidence, message=advance to done 需要用户感知证据，不能只有 pytest -->

    28b. **User-perceivable evidence gate**: When advancing a spec
    to done, the evidence directory must contain at least one
    non-pytest artifact (screenshot, recording, HTTP capture).
    Pure unit-test evidence is insufficient for verifying
    user-facing behavior. Bypass: --force.

<!-- ENFORCE: id=R29b, hook=tool_call, tool=bash, match=vibe(?:\.py)?\s+advance.*review, action=block_no_review_doc, message=advance to review 需要先写 review 文档 -->

    29b. **Review document gate**: When advancing to review,
    a review document must exist in .agents/reviews/.
    Bypass: --force.

<!-- ENFORCE: id=R30b, hook=tool_call, tool=bash, match=vibe(?:\.py)?\s+advance.*released, action=block_no_changelog, message=advance to released 需要 changelog -->

<!-- ENFORCE: id=R69, hook=tool_call, tool=bash, match=vibe(?:\.py)?\s+commit, action=check_ignored_agents, message=.agents/ 文件被 gitignore 时 commit 必须 force-add，否则 ledger sync 假阳性 -->

    69. **.agents/ force-add gate**: When committing, if any
    `.agents/` file is modified but blocked by `.gitignore`, the
    commit wrapper must automatically `git add -f` those files.
    Agent must NOT assume "I edited the file, so it's staged".
    Physical file changes and git index are two different layers.
    If `.gitignore` shields `.agents/archive/` or similar, changes
    to those files are invisible to normal `git add -A`.


    30b. **Changelog gate**: When advancing to released, a
    changelog entry must exist. Bypass: --force --skip-changelog.


    68. **Write-gate: spec state precondition**: Before writing business
    code (files under `src/`, `backend/`, `frontend/`, `lib/`, `app/`,
    or any path listed in `workflow.json.code_paths`), the project
    MUST have at least one spec in `in-progress` status. This gate
    prevents the observed failure mode where an agent skips the
    entire spec/plan/verify workflow and writes code directly from a
    user prompt. The gate only blocks `write`/`edit` tool calls that
    target business code — documentation, tests, config, and
    `.agents/` files are exempt. If no in-progress spec exists, the
    gate blocks with a message directing the agent to create a spec
    first. Projects without `.agents/` (non-vibe projects) are
    automatically skipped. Emergency fixes can bypass via
    `--force` on the `vibe advance` command 
<!-- ENFORCE: id=R53b, hook=tool_call, tool=bash, match=vibe(?:\.py)?\s+commit.*--reviewed, action=block_without_review, message=必须先跑 vibe commit (step 1) 看 diff，才能加 --reviewed -->

<!-- ENFORCE: id=R53c, hook=tool_call, tool=bash, match=vibe(?:\.py)?\s+commit(?!.*--quick), action=block_governance_batch, message=governance文件>5个时必须分commit或用--quick -->
<!-- ENFORCE: id=R53d, hook=tool_call, tool=bash, match=git\s+commit.*/tmp/, action=block_tmp_bypass, message=禁止用 /tmp 脚本绕过 vibe commit，必须用 vibe commit 两步流程 -->

<!-- ENFORCE: id=R8.43, hook=tool_call, tool=bash, match=VIBE_SKIP_COMMIT_MSG_HOOK, action=block_skip_hook, message=禁止跳过 commit-msg hook (VIBE_SKIP_COMMIT_MSG_HOOK)，hook 是门禁不是可选步骤 -->

<!-- ENFORCE: id=R59, hook=tool_call, tool=bash, match=vibe(?:\.py)?\s+advance.*--force, action=block_force_non_emergency, message=--force 仅限 emergency，必须声明 emergency reason 或用 override_approver -->

<!-- ENFORCE: id=R30c, hook=tool_call, tool=bash, match=vibe(?:\.py)?\s+evidence.*observe(?!.*--configured), action=block_observe_no_configured, message=observe evidence 必须带 --configured，否则 Command-Digests 为 N/A -->


    53c. **Governance batch review gate**: When committing, if the
    staged set includes both business code (src/, backend/,
    frontend/) and governance files (.agents/ files), and the
    governance file count exceeds 5, the commit must either:
    (a) use `--quick` (governance-only commits), or (b) split
    into two commits: one for business code (strict review) and
    one for governance (batch). Review-summary line-ref checks
    only apply to business code files. Auto-generated .agents/
    files (evidence, plans, retros) are exempt from per-file
    line-ref requirements.

<!-- ENFORCE: id=R10p, hook=tool_call, tool=bash, match=python3?|pytest, action=block_sandbox_async_db, message=pi sandbox环境跑async DB会hang，必须降级到grep+MagicMock -->

    10p. **Pi sandbox async DB fallback**: In Pi Agent sandbox
    environments, running real async DB operations (e.g.
    `asyncio.run(ensure_default_admin())`) triggers a PTY
    timeout (60s+ hang) because the dev DB lock is held by
    the sandbox process. The verify command must downgrade:
    (1) grep static verification first, (2) MagicMock(spec=[])
    for async DB calls, (3) temp async DB fixture as last
    resort. Never run real async DB writes in sandbox.

<!-- ENFORCE: id=R5c, hook=tool_call, tool=bash, match=vibe(?:\.py)?\s+advance.*review, action=block_solo_review, message=solo session review必须声明待独立reviewer验证 -->

    5c. **Solo session review declaration**: When advancing to
    review in a solo-session (builder == reviewer same session),
    the review document MUST include a "Solo Session Limitation
    Disclosure" section with: (1) a placeholder reviewer session
    ID, (2) a note that independent review is pending, (3) a
    follow-up action item to validate by a future session.
    This prevents self-review from being silently accepted.

<!-- ENFORCE: id=R60f, hook=tool_call, tool=bash, match=vibe(?:\.py)?\s+advance.*done, action=block_unresolved_followup, message=retro含follow-up但未建draft spec不能advance done -->
<!-- ENFORCE: id=R-D-68, hook=tool_call, action=block_direct_spec_status_edit, message=禁止直接改spec状态行，必须用vibe advance让门禁检查evidence/review -->
<!-- ENFORCE: id=R66, hook=tool_call, action=block_no_vibe_status, message=前3次工具调用内必须先跑vibe status+vibe next，禁止凭记忆继续 -->


    60f. **Retro follow-up resolution gate**: When advancing a
    spec to done, if the retro contains a `[follow-up: <id>]`
    item, a draft spec `.agents/specs/<id>.md` MUST exist.
    Follow-ups without corresponding specs signal forgotten
    work. The draft spec must be created in the same commit or
    before advancing to done.


    53b. **Review-then-commit enforcement**: `vibe commit --reviewed`
    MUST NOT be used unless a prior `vibe commit` (step 1, without
    `--reviewed`) was run in the same project first. Step 1 creates
    a `.agents/.vibe-review-pending` marker; step 2 (`--reviewed`)
    consumes it. If the marker is missing, the commit is blocked.
    This prevents the observed failure mode where agents add
    `--reviewed` upfront and never actually read the diff. The
    agent must inspect the diff for unintended modifications,
    scope creep, or regressions before proceeding. `--quick`
    skips this gate for docs-only commits.
to push a spec to
    in-progress without full review.

66. **Session recovery: Agent MUST re-read project state after context loss**: When an Agent's session is interrupted, compacted, restarted, or otherwise loses in-memory context, the Agent MUST NOT continue work based on memory alone. Before doing anything else, the Agent MUST run `vibe status` followed by `vibe next` to re-read the project's `.agents/` state (specs, plans, activity, retros, workflow.json). The Agent MUST then confirm the active spec, current phase, and any open action items with the user before proceeding. This is a structural forcing function: the `.agents/` directory is the single source of truth; an Agent's memory is ephemeral and unreliable after a session break. For multi-turn conversations where `vibe status` was already run in the current session, the Agent MAY skip the re-read, provided it can cite the last known state from the conversation context. When the Agent cannot determine whether the conversation is a continuation or a fresh session, it MUST default to re-reading. This rule applies regardless of the host platform (Codex, Claude Code, Cursor, or any other agent runner).

    **Host Integration Required**: The `templates/agents.md` "Session 恢复与断点续传" section MUST be treated as a mandatory system-prompt prefix. Host implementations SHOULD inject this section at the start of every new session / compact / context switch, or at minimum ensure the Agent reads AGENTS.md before the first user message. The `<!-- AGENT-MANDATORY-FIRST-ACTION -->` HTML comment in the template signals this priority to host tooling. When the host does not support automatic injection, the Agent is responsible for reading AGENTS.md explicitly on session start.

    **Governance batch boundary**: A single commit may touch many
    `.agents/` files when all changes share one root cause (e.g.
    project guidance auto-refresh triggers 70 plan digest updates,
    or a schema version bump). This is distinct from multi-spec
    aggregation (which hides "ghost specs" and is forbidden). A
    governance batch is allowed when:
    1. All changes are auto-refresh output (digest headers only) or
       ≤ 5 lines per file, AND
    2. The commit message declares the single root cause, AND
    3. The review-summary explains why a single batch is justified.
    The auto-stage mechanism (2.7/2.8 segments) ensures refreshed
    files enter the commit rather than staying dirty.


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

## .agents/ Directory Contract

The `.agents/` directory is managed by the Skill. Each subdirectory has a
declared writer, purpose, and lifecycle. Agents must not create subdirectories
not listed here. Each piece of information has exactly one canonical location
(single source of truth).

| Directory | Writer | Purpose | Lifecycle |
|-----------|--------|---------|-----------|
| specs/ | create_spec / spec_amend | Feature specifications | Created to archived |
| plans/ | generate_plan / plan refresh | Implementation plans | Created to archived |
| evidence/ | record_evidence | Verification evidence | Created to archived |
| reviews/ | record_review | Review records | Created to archived |
| retros/ | retrospective | Retrospective records | Written after done, permanent |
| changelogs/ | changelog / commit | Change logs | Archived after release |
| intents/ | create_intent | Intent declarations | Before spec creation |
| reports/ | self_analyze | Structured analysis | Archived to archive/ |
| notes/ | Agent (any) | Temporary notes | No enforced lifecycle |
| archive/ | archive_status | Archived storage | For done/cancelled specs |
| skill-upgrade-candidates/ | Agent / retro | Skill upgrade proposals | Archived after admin review |
| rules/ | Agent / retro | Project-local rules | Adopted or abandoned |
| bugs/ | Agent | Bug inbox (opt-in) | Append-only ledger |
| templates/ | Agent | Prompt templates | Project-specific |

**Key rules**:
- Do not create subdirectories not listed above without Skill update
- `reports/` is a derived view of `retros/`; the source of truth is `retros/`
- `skill-upgrade-proposals/` is deprecated; use `skill-upgrade-candidates/`
- `skill-upgrade-candidates/` filenames must include project slug: `skill-upgrade-candidate-YYYYMMDD-<project-slug>.md` (e.g., `skill-upgrade-candidate-20260719-gemkeep.md`). Multiple proposals same day: append letter suffix (`...-gemkeepb.md`, `...-gemkeepc.md`). This avoids filename collisions when multiple projects submit candidates on the same date.
- `discovery/` files older than 30 days should be archived
- Only one writer owns each directory (no dual-write)

## Project-Level Doctor Auto-Discovery (2026-07-20a)

Projects can place `scripts/doctor_*.py` in their root to add custom health checks.
These are automatically discovered and executed by `vibe doctor` and `vibe advance`.

- `vibe doctor` runs all discovered doctor scripts; failures appear as issues
- `vibe advance` runs only scripts matching the target phase (via `ADVANCE_PHASES:` metadata)
- Default: advisory (warnings only, does not block advance)
- Set `workflow.json` `advance_doctor_gate: "hard"` to make advance block on project doctor failure
- `--force` skips project-level doctor gates (same as other gates)

Doctor script metadata convention:
```python
"""doctor_r_d_58.py — R-D-58 evidence recording order

ADVANCE_PHASES: review, done
"""
```

No `ADVANCE_PHASES:` line means the script runs on all phases.

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

### Plan Header Digest Placeholder Format

When `vibe plan` auto-generates a plan, the header lines `规格摘要:` and
`上下文摘要:` are written with real 16-hex digests computed from spec
content and project-context respectively. **When an Agent manually drafts
a plan file** (using `apply_patch_add_file` etc.), the placeholder MUST be
a 16-character lowercase hex string — `generate_plan.py:200` regex is
strict `[0-9a-f]{16}` and any non-hex placeholder (e.g. `待生成`, `TBD`,
`TBD-on-spec-load`) silently fails to match on `--refresh-digest-only`.

Use these placeholders for manual drafts:

- ✅ `规格摘要: 0000000000000000` (16 zeros)
- ✅ `上下文摘要: 0000000000000000` (16 zeros)
- ❌ `规格摘要: 待生成` (regex fails)
- ❌ `规格摘要: TBD-on-spec-load` (regex fails)

After drafting, run `vibe plan <project_root> <spec_name>
--refresh-digest-only` to replace the placeholder with the real digest.

Why this matters: spec content is hashed (`common.spec_digest`) into a
16-hex digest; any spec change invalidates the plan digest and forces a
re-evidence / re-plan cycle on the next advance. A non-hex placeholder
breaks `refresh` silently — the agent believes the plan was refreshed
but the header still reads `待生成`, which advances fail to detect.

## apply_patch Tool Selection

When editing files, choose the tool by target-content shape. Wrong selection
causes patch metadata to leak into structured files and breaks `spec_digest`
eviction (re-evidence required).

| Tool | Use for | Avoid for |
|---|---|---|
| `apply_patch_replace_file` | Structured text (plan / spec / frontmatter / review / retro / templates / docs that get re-parsed) | None — always safe, just re-types the whole file |
| `apply_patch_update_file` | Business code (`.py` / `.js` / `.ts` / `src/` / `tests/` / single-line tweaks) | Files whose top half is YAML frontmatter (a hunk that crosses `---` will misalign) |
| `apply_patch_batch` | Multiple independent file edits in one call | Single-file edits (use `update_file`); do NOT use to emit raw `*** Begin Patch` blocks into target files — `apply_patch` is parsed by the agent runtime, not stored |

Default selection:

- Plan / spec / spec-status / frontmatter / review / retro → `replace_file`
- Source code under `src/`, `tests/`, `frontend/`, `backend/` → `update_file`
- Bulk operations (clear old evidence + write new evidence across files) → `batch`

Failure mode: writing `*** Begin Patch` and `*** End Patch` literal lines into
a `.md` file via `apply_patch_*` — the agent runtime parses these as patch
metadata, but they end up as visible content. Always review the rendered file
post-patch; if patch metadata appears in the body, re-emit the content via
`replace_file`.

## Suite Architecture

This Skill is the **core** of a suite. Auxiliary Skills (e.g. `vibe-coding-reviewer`)
live as siblings in the same monorepo. The user installs the core once; the core
links each auxiliary on demand via `vibe.py install-auxiliary --all`. Auxiliaries
share the project's `.agents/` state and only contain thin wrappers plus
role-specific instructions — they never duplicate the core's logic or carry
business knowledge. Add a new auxiliary only when a role must be performed by a
separate identity in a fresh session; do not split a single workflow's steps
into multiple Skills.
