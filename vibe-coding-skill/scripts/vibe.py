#!/usr/bin/env python3
"""Single dispatcher for the Vibe Coding workflow.

Codex should invoke this internally after interpreting the user's natural language.
"""

import argparse
import subprocess
import json
import os
import sys
from pathlib import Path

import confirm_risk
import install_auxiliary
import create_retro
import create_intent
import create_spec
import create_ui_contract
import doctor_project
import generate_plan
import generate_prompt
import generate_review
import generate_changelog
import knowledge_gate
import manage_specs
import migrate_project
import archive_status
import commit
import upgrade
import version_bump
import verify_only
import policy_sources
import project_status
import shlex
import record_evidence
import record_review

# 2026-07-10 (09f candidate 2): surfaced in `vibe evidence --help` so
# agents that DO read help get the correct --command invocation
# pattern. R36 misplaced_vibe_options catches the wrong case (vibe
# flag inside --command value); this epilog catches the right case
# (multi-shell-command pipe / quote). Real bug retro: 反思 2 — agent
# passed --command twice and bash ate the second flag as an argument.
EVIDENCE_EPILOG = """\
examples:
  # OK — single shell command:
  vibe evidence . spec-name verify passed --command "pytest tests/ -v"

  # OK — multi-command via bash -c (avoids bash eating --command twice):
  vibe evidence . spec-name verify passed \
    --command "bash -c 'git show HEAD~1:frontend/app.js | grep -n hardcode'"

  # OK — multi-command via pipe:
  vibe evidence . spec-name verify passed \
    --command "git show HEAD~1:frontend/app.js | grep -n hardcode"

  # WRONG (R36 misplaced_vibe_options fail-fast):
  vibe evidence . spec-name verify passed --command pytest --configured

  # WRONG (bash eats second --command):
  vibe evidence . spec-name verify passed --command "git log" --command "pytest -v"

troubleshooting:
  Bash 把 --command 解释成第一个命令的参数 → 用 bash -c 包住整段 shell
  pipe | 在 --command value 里被 quote escape 弄坏 → 用 bash -c 或 shlex 拆分
  vibe flag (--configured / --actor / --role) 出现在 --command 之后 → R36 报错

AC reference format (verify phase 必须):
  ✅ AC1, AC2, AC3, AC4, AC5, AC6, AC7    ← 每个 AC token 单独写
  ✅ AC1 AC2 AC3 AC4 AC5 AC6 AC7           ← 空格分隔
  ❌ AC1-7                                  ← 区间写法, gate 正则只匹配首个数字
  ❌ AC1~7 / AC1..7                         ← 同上

  Gate regex: AC + 可选连字符 + 可选空白 + 数字 (每个 ACn token 必须独立匹配)
  区间写法会被打回, 然后每个 AC 重写一次。Retro: fix-membership-tier-stale-cache
  advance to review 第一次报 "缺少验收标准引用: AC2-AC7", 根因是 description
  写 "AC1-7" — AC1 匹配了, AC2-7 没匹配。

参数位置 (2026-07-11 候选 1):
  vibe evidence <project_root> <spec_name> <phase> <result> [--purpose P] [--configured]

  phase:    observe | release | verify       (位置 3, 必填)
  result:   passed | failed | not-applicable (位置 4, 必填)
  purpose:  --purpose 标志                  (默认 standard, 不是位置参数)

常见错误:
  ❌ vibe evidence . my-spec verify fix-regression passed --configured
     (把 --purpose 值写到 <result> 位置, argparse 报 invalid choice: 'fix-regression')
  ✅ vibe evidence . my-spec verify passed --purpose fix-regression --configured

  ❌ vibe evidence . my-spec verify passed
     (缺 non-empty evidence 描述, gate 报 "证据说明不能为空")
  ✅ vibe evidence . my-spec verify passed "ran pytest tests/ -v"
  ✅ vibe evidence . my-spec verify passed --command "pytest tests/ -v"
"""

import refresh_context
import rule_status
import set_status
import self_analyze
import spec_amend
import retrospective
import update_agents


_ADVANCE_EPILOG = """\
Review-separation escape hatch (single-actor projects):

  When workflow.json.review_separation.required_for contains the spec's
  risk level (defaults to ["high"]; add "medium" to opt in) and the
  project genuinely has no second human identity available, advance to
  released/done can declare the override inline:

      vibe advance <spec> released \\
        --actor <identity> \\
        --role override_approver \\
        --reason "<why>"

  All three conditions are enforced by the advance gate:
    (a) role must be exactly "override_approver";
    (b) --reason must be non-empty (audit trail);
    (c) --actor must equal workflow.json roles.override_approver,
        so a forged override is rejected by the identity check.

  This is narrower than --force, which skips every gate. Other review
  checks (review file exists, approved, has basis, has evidence,
  context/snapshot digest, reviewer identity, decision validity,
  clean worktree) still run under the override.

  Helper Skills 'vibe-coding-reviewer' / 'vibe-coding-debugger' in a
  fresh session are preferred whenever a second identity is reachable.
  Reserve the override for solo work where no second session is
  feasible; reserve --force for emergencies and log --reason.
"""

def main() -> None:
    parser = argparse.ArgumentParser(description="Unified Vibe Coding workflow dispatcher")
    sub = parser.add_subparsers(dest="operation", required=True)

    for name in ("status", "next", "migrate", "doctor", "context-refresh"):
        command = sub.add_parser(name)
        command.add_argument("project_root")
        if name == "migrate":
            command.add_argument("--apply", action="store_true")
        if name == "doctor":
            command.add_argument("--smoke", action="store_true")
        # P1+ (2026-07-11): escape hatch for self_analyze auto-fire
        # in `vibe next` — when test environments or batch jobs need to
        # bypass the analyzer (eg, freeze retros to compare scan output,
        # or sandbox without .agents/retros/ written yet).
        command.add_argument("--skip-self-analyze", action="store_true")
        # P1+ architecture (2026-07-11): escape hatch for upgrade_signals
        # auto-fire — when batch jobs want only retros-based signals and
        # don't want proposal-file scans polluting the aggregator output.
        command.add_argument("--skip-upgrade-signals", action="store_true")

    install_aux = sub.add_parser("install-auxiliary")
    install_aux.add_argument("name", nargs="?", default="")
    install_aux.add_argument("--all", action="store_true")
    install_aux.add_argument("--suite-root", default="<inferred>")
    install_aux.add_argument("--codex-home", default=os.path.expanduser("~/.codex"))
    install_aux.add_argument("--force", action="store_true")
    install_aux.add_argument("--list", action="store_true")

    specs = sub.add_parser("specs")
    specs.add_argument("project_root")
    specs.add_argument("--conflicts", action="store_true")
    specs.add_argument("--priority", action="store_true")

    boundary = sub.add_parser("boundary")
    boundary.add_argument("project_root")
    boundary.add_argument("--skill-root", default=os.path.dirname(os.path.dirname(__file__)))

    intent = sub.add_parser("intent")
    intent.add_argument("project_root")
    intent.add_argument("name")

    spec = sub.add_parser("spec")
    spec.add_argument("project_root")
    spec.add_argument("name")
    spec.add_argument("--type", choices=["feature", "bug", "refactor"], default="feature")
    spec.add_argument("--risk", choices=["low", "medium", "high"], default="medium")
    spec.add_argument("--owner", default="")
    spec.add_argument("--depends-on", default="无")
    spec.add_argument("--release-group", default="")
    spec.add_argument("--regression-from", default="")

    for name in ("plan", "prompt", "review"):
        command = sub.add_parser(name)
        command.add_argument("project_root")
        command.add_argument("spec_name")
        if name == "review":
            command.add_argument("--reviewer", default="")
        if name == "plan":
            command.add_argument(
                "--force",
                action="store_true",
                help="Overwrite an existing plan",
            )
            command.add_argument(
                "--refresh-context",
                action="store_true",
                help=(
                    "Refresh an existing plan's spec and project-context "
                    "digests after adopted rules, AGENTS.md, or other "
                    "project guidance change; archives the previous plan."
                ),
            )
            command.add_argument(
                "--refresh-digest-only",
                action="store_true",
                help=(
                    "Patch only the spec + context digest header lines on "
                    "an existing plan, leaving the plan body untouched. "
                    "Use this when a small spec edit only changed the "
                    "digest (eg added/removed a Risk 确认), not the scope. "
                    "Unlike --refresh-context, this works regardless of "
                    "spec status (done/released are valid) because it does "
                    "not re-render the plan from template."
                ),
            )

    for name in ("ui-contract", "ui-redesign-contract"):
        command = sub.add_parser(name)
        command.add_argument("project_root")
        command.add_argument("spec_name")
        command.add_argument(
            "--source-type",
            default="manual",
            choices=sorted(create_ui_contract.SOURCE_TYPES),
        )
        command.add_argument("--source-artifacts", default="")
        command.add_argument("--generated-by", default="")
        command.add_argument(
            "--model-capability",
            default="unknown",
            choices=sorted(create_ui_contract.MODEL_CAPABILITIES),
        )

    changelog_cmd = sub.add_parser("changelog")
    changelog_cmd.add_argument("project_root")
    changelog_cmd.add_argument("--version", default="")
    changelog_cmd.add_argument("--force", action="store_true")
    changelog_cmd.add_argument("--release-group", default="")

    retro = sub.add_parser("retro")
    retro.add_argument("project_root")
    retro.add_argument("spec_name")

    retrospective_cmd = sub.add_parser("retrospective")
    retrospective_cmd.add_argument("project_root")
    retrospective_cmd.add_argument("spec_name", nargs="?", default="")
    retrospective_cmd.add_argument(
        "--strict", action="store_true",
        help="严格模式: 结论证据缺失时 fail-fast (默认仅 warning, 候选 2 retro 落地)",
    )

    self_analyze_cmd = sub.add_parser("self-analyze")
    self_analyze_cmd.add_argument("project_root")
    self_analyze_cmd.add_argument("--output", default="")

    advance = sub.add_parser(
        "advance",
        epilog=_ADVANCE_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    advance.add_argument("project_root")
    advance.add_argument("spec_name")
    advance.add_argument("status", choices=set_status.VALID_STATUSES)
    advance.add_argument("--actor", default="")
    advance.add_argument("--role", default="")
    advance.add_argument("--force", action="store_true")
    advance.add_argument("--reason", default="")
    advance.add_argument("--skip-changelog", action="store_true",
                        help="released 推进时不自动生成 changelog")
    advance.add_argument("--changelog-version", default="",
                        help="released 推进时使用的 changelog 版本号（默认按时间戳）")
    advance.add_argument("--no-checklist", action="store_true",
                        help="跳过 advance 前的 advisory action checklist")

    archive_stale = sub.add_parser("archive-stale")
    archive_stale.add_argument("project_root")
    archive_stale.add_argument("--apply", action="store_true",
                               help="实际移动文件到 .agents/archive/<时间戳>/，默认 dry-run")
    archive_stale.add_argument("--json", action="store_true",
                               help="输出机器可读 JSON")

    evidence = sub.add_parser("evidence")
    evidence.add_argument("project_root")
    evidence.add_argument("spec_name")
    evidence.add_argument("phase", choices=sorted(record_evidence.PHASES))
    evidence.add_argument("result", choices=sorted(record_evidence.RESULTS))
    evidence.add_argument("description", nargs="*", default=[])  # 0+ tokens; shlex.join when dispatching
    evidence.add_argument("--actor", default="")
    evidence.add_argument("--role", default="")
    evidence.add_argument("--command", dest="exec_command", nargs=argparse.REMAINDER)
    evidence.add_argument("--configured", action="store_true")
    evidence.add_argument("--purpose", choices=sorted(record_evidence.PURPOSES), default="standard")
    evidence.epilog = EVIDENCE_EPILOG
    evidence.formatter_class = argparse.RawDescriptionHelpFormatter

    decision = sub.add_parser("review-decision")
    decision.add_argument("project_root")
    decision.add_argument("spec_name")
    decision.add_argument("conclusion", choices=sorted(record_review.CONCLUSIONS))
    decision.add_argument("basis")
    decision.add_argument("evidence")
    decision.add_argument("--reviewer", required=True)
    decision.add_argument("--role", default="")
    decision.add_argument("--reason", default="")

    amend = sub.add_parser("amend")
    amend.add_argument("project_root")
    amend.add_argument("spec_name")
    amend.add_argument("description")
    amend.add_argument("--apply", action="store_true", help="Execute the amend; default is dry-run preview")

    risk = sub.add_parser("risk")
    risk.add_argument("project_root")
    risk.add_argument("spec_name")
    risk.add_argument("risk", choices=sorted(confirm_risk.RISKS))
    risk.add_argument("--reason", required=True)

    rule = sub.add_parser("rule-status")
    rule.add_argument("project_root")
    rule.add_argument("rule_name")
    rule.add_argument("status", nargs="?", choices=sorted(rule_status.RULE_STATUSES))
    rule.add_argument("--reason", default="")

    upgrade_cmd = sub.add_parser("upgrade")
    upgrade_cmd.add_argument("project_root", help="Project root to upgrade")

    version_bump_cmd = sub.add_parser(
        "version-bump",
        help="Skill self-maintenance: write VERSION = <HEAD>-<feat-slug> and land a chore commit. "
             "Run from inside the Skill repo. Idempotent: no-op if HEAD is already a bump commit "
             "and the tree is clean, or if VERSION content already matches what would be written.",
    )

    verify_cmd = sub.add_parser("verify")
    verify_cmd.add_argument("project_root")
    verify_cmd.add_argument(
        "--scope", action="store_true",
        help="Run verify_scope (fast, scoped to changed files) instead of full suite",
    )
    verify_cmd.add_argument(
        "--full", action="store_true",
        help="Run verify_full (includes integration/e2e) instead of default verify",
    )

    commit_cmd = sub.add_parser(
        "commit",
        epilog=getattr(commit, "REVIEW_SUMMARY_TEMPLATE", ""),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commit_cmd.add_argument("project_root")
    commit_cmd.add_argument(
        "git_args", nargs=argparse.REMAINDER,
        help="Arguments forwarded to `git commit`",
    )
    commit_cmd.add_argument(
        "--no-verify", action="store_true",
        help="Skip Rule 53 verify gate (escape hatch)",
    )
    commit_cmd.add_argument(
        "--no-async-gate", action="store_true",
        help="Skip Rule 64 advisory scan (asyncio.create_task + shared "
             "AsyncSession commit pattern). The scan is advisory only; "
             "this escape hatch is for actor-model projects with independent "
             "session factories or one-shot background writes that have "
             "already been audited.",
    )
    commit_cmd.add_argument(
        "--staged", action="store_true",
        help="Commit only what is already staged (no auto `git add -A`). "
        "Use with `git add <paths>` to split a dirty tree into multiple "
        "focused commits, one per logical unit.",
    )
    commit_cmd.add_argument(
        "--paths", nargs="+", metavar="PATHS",
        help="Stage only the given paths (comma-separated or repeated), "
        "then commit. Most explicit way to scope a commit to a specific "
        "logical unit when the worktree has many pending changes.",
    )
    commit_cmd.add_argument(
        "--full-verify", action="store_true",
        help="Run verify_full (full test suite) instead of verify_scope. "
        "Use for the final commit in a batch to confirm complete integration.",
    )
    commit_cmd.add_argument(
        "--reviewed", action="store_true",
        help="Declare that you have inspected the diff content (Rule 53 review gate). "
        "Without this flag, vibe commit blocks at the review step.",
    )
    commit_cmd.add_argument(
        "--quick", action="store_true",
        help="Skip review gate for docs-only or low-risk commits. "
        "Still runs verify. Trailer becomes Vibe-Commit: quick.",
    )
    commit_cmd.add_argument(
        "--review-summary",
        help="Mandatory with --reviewed: a short description of what you actually "
        "found while reading the diff. Empty string is rejected (exit 7). "
        "Non-empty value is written to the commit as Review-Summary: <text> trailer.",
    )

    policy_scan = sub.add_parser("policy-scan")
    policy_scan.add_argument("project_root")
    policy_scan.add_argument("--apply", action="store_true")

    policy_add = sub.add_parser("policy-conflict-add")
    policy_add.add_argument("project_root")
    policy_add.add_argument("conflict_id")
    policy_add.add_argument("--topic", required=True)
    policy_add.add_argument("--sources", required=True)
    policy_add.add_argument("--severity", choices=sorted(policy_sources.SEVERITIES), required=True)
    policy_add.add_argument("--description", required=True)
    policy_add.add_argument("--scope", default="*")

    policy_resolve = sub.add_parser("policy-conflict-resolve")
    policy_resolve.add_argument("project_root")
    policy_resolve.add_argument("conflict_id")
    policy_resolve.add_argument("--resolution", required=True)
    policy_resolve.add_argument("--accept", action="store_true")

    policy_override = sub.add_parser("policy-override-add")
    policy_override.add_argument("project_root")
    policy_override.add_argument("source_id")
    policy_override.add_argument("--reason", required=True)
    policy_override.add_argument("--actor", default="")

    update_agents_cmd = sub.add_parser("update-agents")
    update_agents_cmd.add_argument("project_root")
    update_agents_cmd.add_argument("--force", action="store_true")

    args = parser.parse_args()

    # install-auxiliary: project_root 不需要；直接转发到 install_auxiliary.main()
    if args.operation == "install-auxiliary":
        saved_argv = sys.argv
        try:
            argv = [saved_argv[0]]
            if args.list:
                argv.append("--list")
            if args.all:
                argv.append("--all")
            if args.name:
                argv.append(args.name)
            if args.suite_root != "<inferred>":
                argv += ["--suite-root", args.suite_root]
            if args.codex_home != os.path.expanduser("~/.codex"):
                argv += ["--codex-home", args.codex_home]
            if args.force:
                argv.append("--force")
            sys.argv = argv
            install_auxiliary.main()
        finally:
            sys.argv = saved_argv
        return

    # version-bump is self-maintenance; doesn't need a project_root.
    if args.operation == "version-bump":
        raise SystemExit(version_bump.bump())

    root = os.path.abspath(args.project_root)
    if args.operation == "status":
        project_status.project_status(root)
    elif args.operation == "next":
        project_status.project_next(root, args=args)
    elif args.operation == "migrate":
        migrate_project.migrate_project(root, args.apply)
    elif args.operation == "specs":
        manage_specs.manage_specs(
            root, show_conflicts=args.conflicts, show_priority=args.priority
        )
    elif args.operation == "doctor":
        result = doctor_project.doctor(root)
        if getattr(args, 'smoke', False):
            smoke_result = doctor_project._smoke_commands(root)
            result["smoke"] = smoke_result
            if smoke_result:
                for cmd_result in smoke_result:
                    if not cmd_result.get("passed"):
                        result["issues"].append(
                            f"smoke: {cmd_result['phase']} command failed: "
                            f"{cmd_result.get('error', cmd_result.get('argv'))}"
                        )
        raise SystemExit(1 if result["issues"] else 0)
    elif args.operation == "context-refresh":
        refresh_context.refresh_context(root)
    elif args.operation == "update-agents":
        result = update_agents.update_agents(root, args.force)
        print(result["message"])
        if not result["success"]:
            raise SystemExit(1)
    elif args.operation == "boundary":
        result = knowledge_gate.audit_skill(args.skill_root, root)
        knowledge_gate.print_audit(result)
        raise SystemExit(1 if result["issues"] else 0)
    elif args.operation == "intent":
        create_intent.create_intent(root, args.name)
    elif args.operation == "spec":
        create_spec.create_spec(
            root, args.name, args.type, args.risk, args.owner,
            args.depends_on, args.release_group,
            args.regression_from,
        )
    elif args.operation == "plan":
        if getattr(args, "refresh_digest_only", False):
            result = generate_plan.refresh_plan_digests_only(
                root, args.spec_name
            )
        elif getattr(args, "refresh_context", False):
            result = generate_plan.refresh_plan_context(root, args.spec_name)
        else:
            result = generate_plan.generate_plan(
                root, args.spec_name, force=getattr(args, "force", False)
            )
        if not result:
            raise SystemExit(1)
    elif args.operation == "prompt":
        generate_prompt.generate_and_save(root, args.spec_name)
    elif args.operation == "review":
        generate_review.generate_review(root, args.spec_name, args.reviewer)
    elif args.operation in {"ui-contract", "ui-redesign-contract"}:
        result = create_ui_contract.create_ui_contract(
            root,
            args.spec_name,
            redesign=args.operation == "ui-redesign-contract",
            source_type=args.source_type,
            source_artifacts=args.source_artifacts,
            generated_by=args.generated_by,
            model_capability=args.model_capability,
        )
        if not result:
            raise SystemExit(1)
    elif args.operation == "changelog":
        generate_changelog.generate_changelog(
            root, args.version, args.force, args.release_group,
        )
    elif args.operation == "retro":
        create_retro.create_retro(root, args.spec_name)
    elif args.operation == "retrospective":
        result = retrospective.run_retrospective(root, args.spec_name)
        if result is None:
            raise SystemExit(1)
        # 候选 2 retro 落地: --strict 模式下若 retro 内容 claim_evidence_warnings 非空, fail-fast
        if getattr(args, "strict", False):
            retro_path = result.get("retro_file") if isinstance(result, dict) else None
            if retro_path and os.path.exists(retro_path):
                content = open(retro_path, encoding="utf-8").read()
                warnings = create_retro.claim_evidence_warnings(content)
                if warnings:
                    print("❌ --strict 模式下 retro 校验未通过:")
                    for warning in warnings:
                        print(f"   {warning}")
                    raise SystemExit(1)
                print("✅ --strict 模式下 retro 校验通过")
    elif args.operation == "self-analyze":
        findings = self_analyze.analyze(root)
        self_analyze.print_report(findings)
        if args.output:
            path = self_analyze.save_report(findings, args.output)
            print(f"\n📄 报告已保存: {path}")
    elif args.operation == "advance":
        result = set_status.set_status(
            root, args.spec_name, args.status, args.force, args.reason,
            args.actor, args.role,
            auto_changelog=not args.skip_changelog,
            changelog_version=args.changelog_version,
            no_checklist=args.no_checklist,
        )
        if result is None:
            raise SystemExit(1)
    elif args.operation == "archive-stale":
        import json as _json
        findings = archive_status.find_stale(args.project_root)
        if args.json:
            print(_json.dumps({"stale": findings, "applied": args.apply}, ensure_ascii=False, indent=2))
            if not args.apply or not findings:
                return
        if not findings:
            print("✅ 没有发现陈旧文件 (.agents/archive 不会被扫描)")
            return
        print(f"📦 发现 {len(findings)} 个陈旧文件:")
        for finding in findings:
            print(f"   - [{finding['kind']}] {finding['path']}  ({finding['age_days']}d / 阈值 {finding['threshold_days']}d)")
            print(f"       {finding['reason']}")
        if not args.apply:
            print("\nℹ️  这是 dry-run。要执行归档，运行: vibe archive-stale <project_root> --apply")
            return
        moved = archive_status.archive(args.project_root, findings)
        print(f"\n✅ 已归档 {len(moved)} 个文件。")

    elif args.operation == "evidence":
        misplaced = record_evidence.misplaced_vibe_options(args.exec_command)
        if misplaced:
            parser.error(
                "vibe evidence options must appear before --command: "
                + ", ".join(misplaced)
            )
        # argparse.REMAINDER keeps quoted strings as one token. Resplit with
        # shlex so a quoted command such as `node /tmp/x.cjs` becomes the
        # argv list ['node', '/tmp/x.cjs']. If the user already passed an
        # unquoted argv, joining then splitting is a no-op.
        exec_command = None
        if args.exec_command:
            exec_command = shlex.split(" ".join(args.exec_command))
        # description is now nargs="*" (list of tokens); shlex.join to restore the
        # user-typed free-form string. Empty list joins to "" (record_evidence
        # raises ValueError when both evidence and command are empty).
        description_text = shlex.join(args.description) if args.description else ""
        result = record_evidence.record_evidence(
            root, args.spec_name, args.phase, args.result, description_text,
            args.actor, args.role, exec_command,
            args.configured, args.purpose,
        )
        if result is None:
            raise SystemExit(1)
        # Verify passed → print a compact next-action hint (Rule 22 follow-through).
        # Only fire when evidence actually recorded AND it was verify+passed, so
        # failed reproduction or release/observe evidence don't get a "advance"
        # suggestion they shouldn't act on.
        if (
            result is not None
            and args.phase == "verify"
            and args.result == "passed"
            and args.purpose == "standard"
        ):
            project_status.post_verify_hint(root, args.spec_name)
    elif args.operation == "review-decision":
        result = record_review.record_review(
            root, args.spec_name, args.conclusion, args.basis,
            args.evidence, args.reviewer,
            role=args.role, reason=args.reason,
        )
        if result is None:
            raise SystemExit(1)
    elif args.operation == "amend":
        spec_amend.amend_spec(root, args.spec_name, args.description, apply=args.apply)
    elif args.operation == "risk":
        confirm_risk.confirm_risk(root, args.spec_name, args.risk, args.reason)
    elif args.operation == "upgrade":
        raise SystemExit(upgrade.upgrade(args.project_root))
    elif args.operation == "version-bump":
        raise SystemExit(version_bump.bump())
    elif args.operation == "verify":
        tier = "verify_full" if getattr(args, "full", False) else ("verify_scope" if getattr(args, "scope", False) else "verify")
        raise SystemExit(verify_only.verify(root, tier))
    elif args.operation == "commit":
        # Build argv for commit.run() from already-parsed args. Flags
        # that could be eaten by argparse.REMAINDER (because they
        # appear inside `git_args`) are pulled out of sys.argv.
        no_verify = "--no-verify" in sys.argv
        no_async_gate = "--no-async-gate" in sys.argv
        full_verify = "--full-verify" in sys.argv
        reviewed = "--reviewed" in sys.argv
        quick = "--quick" in sys.argv
        staged_only = getattr(args, "staged", False)
        paths = getattr(args, "paths", None) or []
        review_summary = getattr(args, "review_summary", None) or ""
        run_argv = [args.project_root, *args.git_args]
        if staged_only:
            run_argv = ["--staged", *run_argv]
        if paths:
            run_argv = ["--paths", ",".join(paths), *run_argv]
        if full_verify:
            run_argv = ["--full-verify", *run_argv]
        if reviewed:
            run_argv = ["--reviewed", *run_argv]
        if quick:
            run_argv = ["--quick", *run_argv]
        if no_verify:
            run_argv = ["--no-verify", *run_argv]
        if no_async_gate:
            run_argv = ["--no-async-gate", *run_argv]
        if review_summary:
            run_argv = ["--review-summary", review_summary, *run_argv]
        raise SystemExit(commit.run(run_argv))
    elif args.operation == "rule-status":
        rule_status.set_rule_status(root, args.rule_name, args.status, args.reason)
    elif args.operation == "policy-scan":
        result = policy_sources.scan_policy_sources(
            Path(root), apply=args.apply
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.operation == "policy-conflict-add":
        result = policy_sources.add_conflict(
            Path(root),
            args.conflict_id,
            args.topic,
            [item.strip() for item in args.sources.split(",") if item.strip()],
            args.severity,
            args.description,
            [item.strip() for item in args.scope.split(",") if item.strip()],
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.operation == "policy-conflict-resolve":
        result = policy_sources.resolve_conflict(
            Path(root),
            args.conflict_id,
            args.resolution,
            "accepted" if args.accept else "resolved",
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.operation == "policy-override-add":
        actor = args.actor.strip() or os.environ.get("USER", "unknown")
        result = policy_sources.add_override(
            Path(root), args.source_id, args.reason, actor,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
