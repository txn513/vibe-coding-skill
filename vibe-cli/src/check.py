"""Phase-based verification checklists."""

CHECKLISTS = {
    "pre-code": {
        "title": "写代码前 — 前置检查",
        "items": [
            ("规格已确认，意图清晰", "spec"),
            ("约束已明确（技术 + 业务 + 不动范围）", "spec"),
            ("验收标准已写清楚正常路径和边界情况", "spec"),
            ("依赖已就绪（API、库、环境）", "env"),
            ("AGENTS.md 和 .agents/rules/ 已更新", "context"),
        ],
    },
    "implementation": {
        "title": "实现中 — 质量检查",
        "items": [
            ("代码编译/构建通过", "build"),
            ("命名符合项目规范", "style"),
            ("没有硬编码密钥/密码/Token", "security"),
            ("外部输入已校验和消毒", "security"),
            ("错误有适当处理，不暴露内部信息", "error"),
            ("新增代码有对应测试", "test"),
            ("没有引入新的第三方依赖（除非规格允许）", "dep"),
        ],
    },
    "review": {
        "title": "审查前 — 准备检查",
        "items": [
            ("所有验收标准已实现", "ac"),
            ("测试覆盖率可接受", "coverage"),
            ("没有遗留调试代码或 console.log", "clean"),
            ("Git diff 清晰、原子化", "git"),
            ("已准备独立审查上下文（vibe review）", "review"),
        ],
    },
    "deploy": {
        "title": "上线前 — 发布检查",
        "items": [
            ("CI/CD 流水线全部通过", "ci"),
            ("数据库迁移可回滚", "db"),
            ("监控和告警已配置", "monitor"),
            ("回滚方案已确认", "rollback"),
            ("灰度/金丝雀发布计划已确认", "release"),
        ],
    },
}


def show_checklist(phase: str) -> None:
    """Display a verification checklist for the given phase."""
    if phase not in CHECKLISTS:
        print(f"❌ 未知阶段: {phase}")
        print(f"   可用阶段: {', '.join(CHECKLISTS.keys())}")
        return

    cl = CHECKLISTS[phase]
    print(f"\n📋 {cl['title']}")
    print("─" * 40)
    for i, (desc, tag) in enumerate(cl["items"], 1):
        print(f"  [{i}] [{tag}] {desc}")
    print("─" * 40)
    print(f"  共 {len(cl['items'])} 项检查")
    print()


def list_phases() -> None:
    """List all available checklist phases."""
    print("\n可用的验证阶段:\n")
    for phase, cl in CHECKLISTS.items():
        print(f"  {phase:20s} → {cl['title']}")
    print()
