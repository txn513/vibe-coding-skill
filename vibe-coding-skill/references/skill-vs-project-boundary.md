# Skill 核心 vs 项目规则 — 分界速查

> 通用参考文档。供任何接入 Vibe Coding Skill 的项目 agent 在判断"这条约束来自哪"时查阅。
> 不绑特定项目、不绑特定技术栈、不绑特定 retro。

## 一句话原则

> **"必须做某类治理动作"** → Skill 管
> **"用什么工具 / 什么错误码 / 什么命名 / 什么默认值"** → 项目管

详细分类见 Rule 20 (`SKILL.md`)。

## Skill 核心升级 vs 项目级落地 — 区分模板

每次有新治理动作，按下面三步判断它该去哪里：

1. **剥项目特定词**：人名 / 项目名 / 框架名 / 工具名 / 端口 / 错误码词汇 / 进程隔离方式 / 命名约定 —— 一律进项目。
2. **剩下的"必须做某事"**才是 governance 候选。
3. **写进 Skill 之前问一句**："任何接入 Skill 的项目都会撞到这条问题吗？" 是 → 进 Skill；否 → 留项目。

## 通用边界速查表

下面这张表覆盖高频决策。每一行**左侧是治理动作**，**右侧写明哪边负责**。

| 治理动作 | Skill 怎么定 | 项目怎么定 |
|---|---|---|
| spec 触及多进程链路时必须规划降级路径 | Rule 12 子条款要求"valid / degraded / recovered"三态验证 | 反向代理工具、错误码词汇、进程隔离方式 |
| spec 涉及 Rule 12 / Rule 13 时必须有 testing rule 覆盖 | Rule 15 在 spec-ready 阶段阻断 | testing rule 本身的内容 |
| spec 涉及 Rule 12 / Rule 13 时，verify 阶段补三态证据 | Rule 12 / Rule 13 要求 | 证据的具体形式（脚本 / 截图 / 日志） |
| 写操作 spec 必须列出受影响的读路径 | Rule 44 强制 | 读路径如何失效 / 主动失效的具体方法 |
| 高风险 spec 必须有独立审查者 | Rule 5（默认仅 high 强制） | `workflow.json.review_separation.required_for` opt-in 加入 `"medium"` / `"low"` |
| 独立审查者具体怎么实现 | Rule 5 故意不绑机制 | 项目运行时选独立 sub-agent / 新 session / helper Skill |
| 验证证据必须 per-AC 引用 | Rule 30 / Rule 31 强制 | AC 的具体内容、证据 artifact 形式 |
| plan checkbox 应随实施同步 | Rule 43（advisory） | 项目可以在 `.agents/rules/plan-sync.md` 改为强制 |
| 阶段推进必须经闸门 | Rule 22（stage-transition gate） | 闸门里各检查项的强度（`workflow.json.risk_profiles`） |
| 每个 spec 必须有 Intent / 验证方式 / 验收标准 | Rule 6 / Rule 15 / Rule 26 | 各项的具体内容、AC 编号命名 |
| Bug spec 必须有 reproduction + fix-regression 双向证据 | 通用治理要求 | reproduction 脚本、regression 测试位置 |
| 涉及外部系统的 spec 必须声明如何集成 | Rule 21 要求"integrate external systems instead" | 集成方式、配置位置、凭据管理 |
| 阶段停留超时应被 status 标出 | Rule 46（stage-stall observable） | SLA 阈值（`workflow.json.stage_stall_sla`） |
| 陈旧证据 / 规则 / spec 应被归档 | Rule 45 + archive 配置 | 阈值（`workflow.json.archive.thresholds_days`） |

## 怎么判断"这条规则该进 Skill 还是留项目"

回答下面 5 个问题，全部答"是"才能进 Skill：

1. **跨项目可复用吗？** 任意两个技术栈不同的项目都会撞到这条问题。
2. **剥掉项目特定词之后还有可执行内容吗？** 如果剥完只剩"我们项目应该……"，留项目。
3. **不会强制项目做超出治理范围的事吗？** 比如"必须接入 k8s"或"必须用 XX 监控"——这些进 Skill 就是 Rule 21 越界。
4. **不会让 Skill 体积膨胀但效果微弱吗？** 一句话能写清的就别开新规则号。
5. **不会和现有 Rule 重复吗？** 比如新规则其实是 Rule 12 的子条款，那就加进 Rule 12 末尾而不是新开 12a。

任何一条答"否"，留项目。

## 项目级规则的常见位置

项目 agent 通常把"自己定的实现细节"放在这些位置。Skill 不管也不该管：

- `.agents/AGENTS.md` — 项目技术栈、当前阶段、不让 Agent 做的事
- `.agents/rules/*.md` — 项目特定的编码/测试/审查约定
- `.agents/workflow.json` — 治理字段的项目级覆盖（`risk_profiles`、`commands`、`model_tiers`、`review_separation.required_for` 等）
- `.agents/policy-differences.md` — 项目与 Skill 默认规范有差异的待确认项
- `.agents/specs/<name>.md` — 具体功能的 AC、范围、验证方式（Rule 6 要求）
- `.agents/plans/<name>.md` — 实施计划
- `.agents/reviews/<name>.md` — 审查记录
- `.agents/retros/<name>.md` — 复盘

## 当项目 retro 想推动 Skill 升级时

按 Rule 16 顺序：

1. **先尝试更新本项目的 rules / docs / retros / testing policy**。这条解决"本项目踩的坑"。
2. **剥掉项目特定词，看剩余是否仍是 governance 候选**。是 → 写成 Skill 升级提案。
3. **Skill 升级必须经用户显式确认**（Rule 17）—— self_analyze 和 retro 只能"发现"，不能"授权"。

边界审计命令：

```bash
python3 <skill>/scripts/vibe.py boundary <project_root>
```

无输出 = 干净；任何 "deterministic boundary violation" = Skill 已经被项目特定词污染。

## 容易混淆的边界情况

| 看起来像 | 实际是 | 怎么办 |
|---|---|---|
| "我们项目要用 Vite proxy 兜底 503 JSON" | 项目特定实现 | 留 `.agents/rules/api-resilience.md` |
| "任何多进程项目都应该让 forwarder 返回结构化错误" | 通用治理 | Rule 12 子条款 |
| "我们项目用 NETWORK_ERROR 表示网络断" | 项目错误码命名 | 留项目 |
| "前端必须能区分网络断和业务 5xx" | 通用治理 | Rule 12 子条款 |
| "我们项目 high risk 也允许 builder 自审" | 项目想放松 Skill 默认 | `workflow.json.review_separation.required_for = ["medium"]`（保留 high 不强制）—— 不行，必须重写闸门逻辑 |
| "我们项目用 Open Design 做 UI 设计" | 外部工具集成 | 留项目；Rule 40 治理"如何接入外部 UI 工具"|
| "我们项目用 GitLab 而非 GitHub" | 工具替换 | 留项目；Rule 21 鼓励"integrate external systems"|

## 一句话总结

> Skill 管"做什么"，项目管"用什么做"。

具体动作：把治理动作放 Skill Rule，把实现细节放 `.agents/rules/*.md`，把项目特定数据放 `.agents/specs/`。三者之间用 `workflow.json` 字段做"项目级覆盖 Skill 默认"的通道。
