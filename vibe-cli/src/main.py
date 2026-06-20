import argparse
import importlib
import os
import subprocess
import sys


def _import_module(name: str):
    """Import a sibling module from the src directory."""
    return importlib.import_module(name)


def resolve_project_root() -> str:
    """Walk up from cwd to find AGENTS.md or .agents/ directory."""
    d = os.getcwd()
    while True:
        if os.path.exists(os.path.join(d, "AGENTS.md")) or \
           os.path.exists(os.path.join(d, ".agents")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return os.getcwd()


def resolve_skill_script() -> str:
    """Locate the sibling vibe-coding-skill dispatcher script."""
    env_root = os.environ.get("VIBE_SKILL_ROOT")
    candidates = []
    if env_root:
        candidates.append(os.path.join(env_root, "scripts", "vibe.py"))
    candidates.append(
        os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "vibe-coding-skill", "scripts", "vibe.py")
        )
    )

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    raise FileNotFoundError(
        "未找到 vibe-coding-skill/scripts/vibe.py。"
        " 请设置 VIBE_SKILL_ROOT 或保持 vibe-cli 与 vibe-coding-skill 同级。"
    )


def run_skill(command_args: list[str], project_root: str) -> None:
    """Delegate command execution to the workflow dispatcher."""
    script = resolve_skill_script()
    result = subprocess.run([sys.executable, script, *command_args], cwd=project_root)
    if result.returncode:
        raise SystemExit(result.returncode)


def main():
    parser = argparse.ArgumentParser(
        prog="vibe",
        description="Vibe Coding 工作流工具 — 从意图到上线的每个阶段",
    )
    sub = parser.add_subparsers(dest="command", help="可用命令")

    # init
    p_init = sub.add_parser("init", help="初始化项目 Vibe Coding 结构")
    p_init.add_argument("path", nargs="?", default=".", help="项目路径 (默认: 当前目录)")
    p_init.add_argument("--type", choices=["web", "api", "cli"], default="web",
                        help="项目类型 (默认: web)")

    # spec
    p_spec = sub.add_parser("spec", help="创建功能规格")
    p_spec.add_argument("name", help="功能名称 (用作文件名)")
    p_spec.add_argument("--type", choices=["feature", "bug", "refactor"], default="feature",
                        help="规格类型 (默认: feature)")
    p_spec.add_argument("--risk", choices=["low", "medium", "high"], default="medium",
                        help="风险等级 (默认: medium)")
    p_spec.add_argument("--owner", default="", help="负责人")
    p_spec.add_argument("--depends-on", default="无", help="依赖规格，逗号分隔或填 无")
    p_spec.add_argument("--release-group", default="", help="发布组")
    p_spec.add_argument("--regression-from", default="", help="回归来源规格（bug 修复时可选）")

    # specs (list)
    sub.add_parser("specs", help="列出所有功能规格")

    # plan
    p_plan = sub.add_parser("plan", help="从规格生成实施计划")
    p_plan.add_argument("spec_name", help="规格名称（不含 .md）")
    p_plan.add_argument(
        "--refresh-context",
        action="store_true",
        help="刷新现有 plan 的 spec 与项目上下文摘要 (adopted rules / AGENTS.md 变动后使用)",
    )

    # prompt
    p_prompt = sub.add_parser("prompt", help="为规格生成实现 Agent Prompt")
    p_prompt.add_argument("spec_name", help="规格名称（不含 .md）")

    # check
    p_check = sub.add_parser("check", help="显示阶段验证清单")
    p_check.add_argument("phase", nargs="?", default=None,
                         help="阶段名: pre-code, implementation, review, deploy")

    # review
    p_review = sub.add_parser("review", help="生成独立审查上下文")
    p_review.add_argument("spec_name", help="关联的规格名称（不含 .md）")
    p_review.add_argument("--reviewer", default="", help="审查人")

    for command_name, help_text in (
        ("ui-contract", "为 UI 需求生成治理化设计合同"),
        ("ui-redesign-contract", "为老项目 UI 重设计生成保留/替换边界合同"),
    ):
        p_ui = sub.add_parser(command_name, help=help_text)
        p_ui.add_argument("spec_name", help="关联的规格名称（不含 .md）")
        p_ui.add_argument(
            "--source-type",
            default="manual",
            choices=["figma", "manual", "mixed", "opendesign", "other", "penpot", "screenshot"],
            help="设计来源类型",
        )
        p_ui.add_argument("--source-artifacts", default="", help="设计产物路径、链接或说明")
        p_ui.add_argument("--generated-by", default="", help="设计来源工具、Agent 或人工来源")
        p_ui.add_argument(
            "--model-capability",
            default="unknown",
            choices=["mixed", "multimodal", "text-only", "unknown"],
            help="后续实现模型能力",
        )

    p_retro = sub.add_parser("retro", help="为已完成规格创建回顾")
    p_retro.add_argument("spec_name", help="关联的规格名称（不含 .md）")

    p_retrospective = sub.add_parser("retrospective", help="运行一次项目内复盘动作")
    p_retrospective.add_argument("spec_name", nargs="?", default="", help="关联的规格名称（不含 .md）；省略时自动定位最近完成的 spec")

    p_self_analyze = sub.add_parser("self-analyze", help="聚合分析多个回顾，发现重复模式")
    p_self_analyze.add_argument("--output", default="", help="可选：将分析报告保存到文件")

    p_changelog = sub.add_parser("changelog", help="从已完成规格生成 changelog")
    p_changelog.add_argument("--version", default="", help="版本号（如 v1.2.0）")
    p_changelog.add_argument("--force", action="store_true", help="覆盖已存在 changelog（先备份）")
    p_changelog.add_argument("--release-group", default="", help="只包含该发布组")

    # workflow commands delegated to vibe.py
    sub.add_parser("status", help="显示项目全局状态概览")
    sub.add_parser("next", help="给出当前项目最值得做的下一步")
    sub.add_parser("context-refresh", help="刷新项目上下文并更新 AGENTS.md")

    p_doctor = sub.add_parser("doctor", help="诊断工作流完整性")
    p_doctor.add_argument("--smoke", action="store_true", help="运行配置的验证命令")
    p_migrate = sub.add_parser("migrate", help="迁移旧版工作流元数据")
    p_migrate.add_argument("--apply", action="store_true", help="写回迁移结果")

    p_boundary = sub.add_parser("boundary", help="审计 Skill 与项目边界")
    p_boundary.add_argument("--skill-root", default="", help="Skill 根目录（可选）")

    p_intent = sub.add_parser("intent", help="创建发现记录")
    p_intent.add_argument("name", help="记录名称")

    p_advance = sub.add_parser("advance", help="推进规格状态并执行门禁检查")
    p_advance.add_argument("spec_name", help="规格名称（不含 .md）")
    p_advance.add_argument("status", help="目标状态")
    p_advance.add_argument("--actor", default="", help="操作者")
    p_advance.add_argument("--role", default="", help="操作者角色")
    p_advance.add_argument("--force", action="store_true", help="强制推进")
    p_advance.add_argument("--reason", default="", help="强制推进原因")
    p_advance.add_argument("--skip-changelog", action="store_true",
                           help="released 推进时不自动生成 changelog")
    p_advance.add_argument("--changelog-version", default="",
                           help="released 推进时使用的 changelog 版本号")

    p_archive_stale = sub.add_parser("archive-stale", help="扫描并归档陈旧 .agents/ 文件 (Rule 45)")
    p_archive_stale.add_argument("project_root", nargs="?", default="", help="项目根目录；省略时使用当前目录或 AGENTS.md 自动探测")
    p_archive_stale.add_argument("--apply", action="store_true", help="实际移动文件到 .agents/archive/<时间戳>/，默认 dry-run")
    p_archive_stale.add_argument("--json", action="store_true", help="输出机器可读 JSON")

    p_evidence = sub.add_parser("evidence", help="记录验证、发布或观察证据")
    p_evidence.add_argument("spec_name", help="规格名称（不含 .md）")
    p_evidence.add_argument("phase", help="阶段：verify/release/observe")
    p_evidence.add_argument("result", help="结果：passed/failed/not-applicable")
    p_evidence.add_argument("description", nargs="?", default="", help="补充说明")
    p_evidence.add_argument("--actor", default="", help="操作者")
    p_evidence.add_argument("--role", default="", help="操作者角色")
    p_evidence.add_argument("--configured", action="store_true", help="执行 workflow 配置的命令")
    p_evidence.add_argument("--purpose", default="standard", help="证据用途")
    p_evidence.add_argument("--command", dest="exec_command", nargs=argparse.REMAINDER,
                            help="执行真实命令并记录输出；放在最后")

    p_review_decision = sub.add_parser("review-decision", help="提交结构化审查结论")
    p_review_decision.add_argument("spec_name", help="规格名称（不含 .md）")
    p_review_decision.add_argument("conclusion", help="审查结论")
    p_review_decision.add_argument("basis", help="审查依据")
    p_review_decision.add_argument("evidence", help="审查证据")
    p_review_decision.add_argument("--reviewer", required=True, help="审查人")

    p_amend = sub.add_parser("amend", help="记录需求变更并归档过期产物")
    p_amend.add_argument("spec_name", help="规格名称（不含 .md）")
    p_amend.add_argument("description", help="变更说明")

    p_risk = sub.add_parser("risk", help="确认规格风险等级")
    p_risk.add_argument("spec_name", help="规格名称（不含 .md）")
    p_risk.add_argument("risk", choices=["low", "medium", "high"], help="风险等级")
    p_risk.add_argument("--reason", required=True, help="确认理由")

    p_rule_status = sub.add_parser("rule-status", help="查看或更新项目规则状态")
    p_rule_status.add_argument("rule_name", help="规则文件名（不含 .md）")
    p_rule_status.add_argument("status", nargs="?", help="目标状态")
    p_rule_status.add_argument("--reason", default="", help="状态变更原因")

    p_policy_scan = sub.add_parser("policy-scan", help="扫描已有规范来源")
    p_policy_scan.add_argument("--apply", action="store_true", help="写入扫描结果")

    p_policy_add = sub.add_parser("policy-conflict-add", help="记录显式规范冲突")
    p_policy_add.add_argument("conflict_id", help="冲突 ID")
    p_policy_add.add_argument("--topic", required=True, help="冲突主题")
    p_policy_add.add_argument("--sources", required=True, help="来源 ID，逗号分隔")
    p_policy_add.add_argument("--severity", required=True, choices=["low", "medium", "high"],
                              help="冲突等级")
    p_policy_add.add_argument("--description", required=True, help="冲突说明")
    p_policy_add.add_argument("--scope", default="*", help="影响范围，逗号分隔")

    p_policy_resolve = sub.add_parser("policy-conflict-resolve", help="解决显式规范冲突")
    p_policy_resolve.add_argument("conflict_id", help="冲突 ID")
    p_policy_resolve.add_argument("--resolution", required=True, help="解决方案")
    p_policy_resolve.add_argument("--accept", action="store_true", help="标记为 accepted")

    p_install_aux = sub.add_parser("install-auxiliary", help="把套件中的辅助 Skill 链接到 ~/.codex/skills/")
    p_install_aux.add_argument("name", nargs="?", default="", help="辅助 Skill 名；省略时配合 --all 扫描同级")
    p_install_aux.add_argument("--all", action="store_true", help="扫描 suite 根目录，安装所有辅助")
    p_install_aux.add_argument("--suite-root", default="", help="套件根目录（默认按 monorepo 推断）")
    p_install_aux.add_argument("--codex-home", default="", help="Codex 配置目录（默认 ~/.codex）")
    p_install_aux.add_argument("--force", action="store_true", help="覆盖已存在链接或目录")
    p_install_aux.add_argument("--list", action="store_true", help="仅列出可安装的辅助")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    project_root = resolve_project_root()

    if args.command == "init":
        scaffold = _import_module("scaffold")
        target = os.path.abspath(args.path)
        scaffold.init_project(target, args.type)

    elif args.command == "spec":
        run_skill([
            "spec",
            project_root,
            args.name,
            "--type", args.type,
            "--risk", args.risk,
            "--owner", args.owner,
            "--depends-on", args.depends_on,
            "--release-group", args.release_group,
            "--regression-from", args.regression_from,
        ], project_root)

    elif args.command == "specs":
        spec_mod = _import_module("spec")
        specs = spec_mod.list_specs(project_root)
        if specs:
            print(f"\n📂 功能规格 ({len(specs)}):\n")
            for s in specs:
                print(f"  - {s.replace('.md', '')}")
            print()
        else:
            print("📭 暂无功能规格。使用 vibe spec <名称> 创建。")

    elif args.command == "plan":
        command = ["plan", project_root, args.spec_name]
        if getattr(args, "refresh_context", False):
            command.append("--refresh-context")
        run_skill(command, project_root)

    elif args.command == "prompt":
        run_skill(["prompt", project_root, args.spec_name], project_root)

    elif args.command == "check":
        check_mod = _import_module("check")
        if args.phase:
            check_mod.show_checklist(args.phase)
        else:
            check_mod.list_phases()

    elif args.command == "review":
        command = ["review", project_root, args.spec_name]
        if args.reviewer:
            command.extend(["--reviewer", args.reviewer])
        run_skill(command, project_root)

    elif args.command in {"ui-contract", "ui-redesign-contract"}:
        command = [
            args.command,
            project_root,
            args.spec_name,
            "--source-type", args.source_type,
            "--model-capability", args.model_capability,
        ]
        if args.source_artifacts:
            command.extend(["--source-artifacts", args.source_artifacts])
        if args.generated_by:
            command.extend(["--generated-by", args.generated_by])
        run_skill(command, project_root)

    elif args.command == "retro":
        run_skill(["retro", project_root, args.spec_name], project_root)

    elif args.command == "retrospective":
        command = ["retrospective", project_root]
        if args.spec_name:
            command.append(args.spec_name)
        run_skill(command, project_root)

    elif args.command == "self-analyze":
        command = ["self-analyze", project_root]
        if args.output:
            command.extend(["--output", args.output])
        run_skill(command, project_root)

    elif args.command == "changelog":
        command = ["changelog", project_root]
        if args.version:
            command += ["--version", args.version]
        if args.force:
            command.append("--force")
        if args.release_group:
            command += ["--release-group", args.release_group]
        run_skill(command, project_root)

    elif args.command == "status":
        run_skill(["status", project_root], project_root)

    elif args.command == "next":
        run_skill(["next", project_root], project_root)

    elif args.command == "context-refresh":
        run_skill(["context-refresh", project_root], project_root)

    elif args.command == "doctor":
        command = ["doctor", project_root]
        if getattr(args, 'smoke', False):
            command.append("--smoke")
        run_skill(command, project_root)

    elif args.command == "migrate":
        command = ["migrate", project_root]
        if args.apply:
            command.append("--apply")
        run_skill(command, project_root)

    elif args.command == "boundary":
        command = ["boundary", project_root]
        if args.skill_root:
            command.extend(["--skill-root", args.skill_root])
        run_skill(command, project_root)

    elif args.command == "intent":
        run_skill(["intent", project_root, args.name], project_root)

    elif args.command == "advance":
        command = ["advance", project_root, args.spec_name, args.status]
        if args.actor:
            command.extend(["--actor", args.actor])
        if args.role:
            command.extend(["--role", args.role])
        if args.force:
            command.append("--force")
        if args.reason:
            command.extend(["--reason", args.reason])
        if args.skip_changelog:
            command.append("--skip-changelog")
        if args.changelog_version:
            command.extend(["--changelog-version", args.changelog_version])
        run_skill(command, project_root)

    elif args.command == "archive-stale":
        command = ["archive-stale", args.project_root or project_root]
        if args.apply:
            command.append("--apply")
        if args.json:
            command.append("--json")
        run_skill(command, args.project_root or project_root)

    elif args.command == "evidence":
        command = ["evidence", project_root, args.spec_name, args.phase, args.result]
        if args.description:
            command.append(args.description)
        if args.actor:
            command.extend(["--actor", args.actor])
        if args.role:
            command.extend(["--role", args.role])
        if args.configured:
            command.append("--configured")
        if args.purpose:
            command.extend(["--purpose", args.purpose])
        if args.exec_command:
            command.append("--command")
            command.extend(args.exec_command)
        run_skill(command, project_root)

    elif args.command == "review-decision":
        run_skill([
            "review-decision",
            project_root,
            args.spec_name,
            args.conclusion,
            args.basis,
            args.evidence,
            "--reviewer", args.reviewer,
        ], project_root)

    elif args.command == "amend":
        run_skill(["amend", project_root, args.spec_name, args.description], project_root)

    elif args.command == "risk":
        run_skill([
            "risk",
            project_root,
            args.spec_name,
            args.risk,
            "--reason", args.reason,
        ], project_root)

    elif args.command == "rule-status":
        command = ["rule-status", project_root, args.rule_name]
        if args.status:
            command.append(args.status)
        if args.reason:
            command.extend(["--reason", args.reason])
        run_skill(command, project_root)

    elif args.command == "policy-scan":
        command = ["policy-scan", project_root]
        if args.apply:
            command.append("--apply")
        run_skill(command, project_root)

    elif args.command == "policy-conflict-add":
        run_skill([
            "policy-conflict-add",
            project_root,
            args.conflict_id,
            "--topic", args.topic,
            "--sources", args.sources,
            "--severity", args.severity,
            "--description", args.description,
            "--scope", args.scope,
        ], project_root)

    elif args.command == "policy-conflict-resolve":
        command = [
            "policy-conflict-resolve",
            project_root,
            args.conflict_id,
            "--resolution", args.resolution,
        ]
        if args.accept:
            command.append("--accept")
        run_skill(command, project_root)

    elif args.command == "install-auxiliary":
        # 不需要 project_root；直接转发到核心
        command = ["install-auxiliary"]
        if args.list:
            command.append("--list")
        if args.all:
            command.append("--all")
        if args.name:
            command.append(args.name)
        if args.suite_root:
            command += ["--suite-root", args.suite_root]
        if args.codex_home:
            command += ["--codex-home", args.codex_home]
        if args.force:
            command.append("--force")
        run_skill(command, ".")


if __name__ == "__main__":
    main()
