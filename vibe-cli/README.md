# vibe — Vibe Coding 工作流工具

`vibe-cli` 是 `vibe-coding-skill` 的命令行薄封装。它不复制工作流逻辑，只负责把统一的
`vibe <command>` 入口转发到 Skill 脚本。

## 安装

```bash
# 添加到 PATH
export PATH="$PATH:/path/to/vibe-cli"

# 或者创建别名
alias vibe="python3 /path/to/vibe-cli/vibe"
```

依赖：Python 3.10+，无第三方包。

默认要求 `vibe-cli/` 与 `vibe-coding-skill/` 同级。如果 Skill 不在同级目录，设置：

```bash
export VIBE_SKILL_ROOT="/path/to/vibe-coding-skill"
```

## 工作流

```
vibe init .                  # 初始化新项目
vibe status                  # 看当前全局状态
vibe next                    # 看现在最该做什么
vibe context-refresh         # 刷新 AGENTS.md 上下文
vibe spec <功能名>            # 创建规格
vibe plan <spec>             # 生成计划
vibe prompt <spec>           # 生成实现 Prompt
[ Agent 实现... ]
vibe evidence <spec> verify passed --command pytest
vibe review <spec> --reviewer alice
vibe review-decision <spec> approved "..." "..." --reviewer alice
vibe advance <spec> done
vibe retro <spec>
```

## 命令一览

### `vibe init [path] [--type web|api|cli]`

初始化项目，生成：

- `AGENTS.md` — Agent 上下文文件
- `.agents/rules/` — 编码规范（API、数据库、错误处理、安全、前端）
- `.agents/specs/` — 功能规格目录
- `.agents/plans/` — 实施计划目录
- `.agents/reviews/` — 审查记录目录

### `vibe spec <name> [--type feature|bug|refactor] [--risk low|medium|high]`

创建结构化规格，支持风险、依赖、负责人和发布组元数据。

### `vibe specs`

列出所有功能规格。

### `vibe plan <spec-name>`

从规格生成实施计划。

### `vibe prompt <spec-name>`

为实现 Agent 生成单一上下文 Prompt。

### `vibe check [phase]`

分阶段验证清单：

| 阶段 | 用途 |
|------|------|
| `pre-code` | 写代码前检查 |
| `implementation` | 实现中质量检查 |
| `review` | 审查前准备 |
| `deploy` | 上线前检查 |

### `vibe status`

显示项目全局状态、规格进度和工作流概览。

### `vibe next`

给出当前项目最值得做的下一步，并解释为什么不是别的阶段。

### `vibe context-refresh`

扫描项目当前结构，保守刷新 `AGENTS.md` 中可自动确认的上下文字段。

### `vibe doctor`

诊断工作流完整性、schema 状态和关键缺口。

### `vibe migrate [--apply]`

检查或执行工作流 schema 迁移。

### `vibe review <spec-name> --reviewer <name>`

生成独立审查上下文。

### `vibe retro <spec-name>`

为已完成规格创建回顾文件。仍然沿用现有门禁，只有 `done` 状态的规格可以创建回顾。

### `vibe review-decision <spec> <approved|changes-requested> <basis> <evidence> --reviewer <name>`

提交结构化审查结论。

### `vibe advance <spec> <status>`

推进规格状态，并执行对应门禁。

### `vibe evidence <spec> <verify|release|observe> <passed|failed|not-applicable> [description]`

记录证据。常用形式：

```bash
vibe evidence cli-sync verify passed --command echo ok
vibe evidence cli-sync verify passed --configured
```

### `vibe amend <spec> <description>`

记录需求变更，重置风险确认，并归档过期下游产物。

### `vibe risk <spec> <low|medium|high> --reason "..."`

确认规格风险等级。

### `vibe intent <name>`

创建发现记录，适合还不清楚是否进入规格阶段时使用。

### `vibe rule-status <rule-name> [status]`

查看或更新项目规则状态。

### `vibe policy-scan [--apply]`

扫描已有项目规范来源，生成：

- `.agents/policy-sources.json`
- `.agents/policy-differences.md`
- `.agents/policy-confirmations.md`

### `vibe policy-conflict-add ...`

记录显式规范冲突。

### `vibe policy-conflict-resolve ...`

解决已记录的规范冲突。

### `vibe boundary`

审计 Skill 是否被项目知识污染。

## 核心理念

Vibe Coding 不是一句话把代码“抛给 AI”。更稳的方式是：

1. `Intent`：先明确问题和边界
2. `Spec`：把成功标准写清楚
3. `Plan/Prompt`：把实现上下文收束
4. `Evidence/Review`：用证据和独立审查收口

这个 CLI 做的事很简单：把这些阶段变成统一入口，让 Skill 去管真正的治理逻辑。
