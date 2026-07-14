# {{PROJECT_NAME}}

{{PROJECT_DESCRIPTION}}

## Vibe Coding 治理（强制 — 每个环节不可跳过）

**本项目由 Vibe Coding Skill 治理。任何功能、缺陷、重构、交付问题或项目状态查询，都必须通过 Vibe Coding 工作流处理。**

### 流程顺序（不可逆，不可跳过）

Discovery → Spec → Plan → Execute → Verify → Review → Release → Observe → Done → Retro

每个阶段推进前，必须先完成当前阶段的所有门禁，否则不得 advance。

<!-- AGENT-MANDATORY-FIRST-ACTION: 以下段落必须在 Agent 启动 / session 恢复 / compact 后第一秒可见。Host (Codex/Claude/Cursor) 应将此段作为 system prompt 前缀注入，或在 Agent 首次读取 AGENTS.md 时优先展示。 -->

## Session 恢复与断点续传

- **Agent 会话中断后必须先恢复状态再工作**：如果对话被 compact/断连/重启，Agent 在继续任何工作前必须先运行 `vibe status` + `vibe next` 恢复项目状态。不要凭记忆继续，因为内存中的上下文已丢失，而 `.agents/` 文件是唯一可信的状态源
- **恢复后核对**：确认当前激活的 spec、阶段、已完成/未完成项，与用户简报当前状态后再继续
- **禁止假设**：不要因为"我记得上次做到这里"就跳过 vibe status；每次 session 恢复都必须重新读取治理文件
- **所有操作前自检**：在运行 `vibe commit`、`vibe amend` 或任何修改性命令前，如果距离上次 `vibe status` 已超过 5 分钟，必须先运行 `vibe status` 确认当前状态


### 阶段级约束

**1. Discovery（意图澄清）**
- 所有工作项必须先记录意图（intent），才能创建 spec
- 禁止跳过 intent 直接写 spec

**2. Spec（规格定义）**
- 高风险变更必须先确认风险等级（confirm_risk），才能 advance in-progress
- 规格变更后必须重新确认风险等级

**3. Plan（实施计划）**
- 必须有实施计划才能 advance in-progress
- 规格变更后必须重新生成计划

**4. Execute（代码实现）**
- 代码提交必须使用 `vibe commit`（两步 review + verify）
- **禁止直接使用 `git commit`**（绕过 review gate 的 bug 会重复）
- `git commit` 只用于 vibe commit 内部调用，agent 不得直接执行
- 误用 `git commit` 后的修复：`git reset --soft HEAD~1` 然后重新 `vibe commit`

**5. Verify（验证）**
- Bug 修复前必须先复现并记录 reproduction 证据
- 修复后必须记录 fix-regression 证据
- evidence 必须在 advance review 前完成，禁止 advance 后补
- 纯单元测试通过不足够，必须有用户感知证据

**6. Review（审查）**
- 高风险变更必须独立 reviewer（不同 session / sub-agent）
- review-summary 必须包含 per-file 行号引用 + 业务结论
- 禁止跳过 review 直接 advance released

**7. Release（发布）**
- 发布前必须有 release 证据
- 发布必须写 CHANGELOG

**8. Observe（上线观察）**
- 高风险变更必须有 observe 证据才能 advance done
- observe 证据缺 Command-Digests 时，错误信息必须包含 retry 模板

**9. Done（完成）**
- Done 后必须立即写 retro，不能跳过
- 如果 retro 文件存在但全是占位符，advance done 时会报错
- `vibe next` 发现 done spec 缺 retro 时，会强制推荐先写 retro，不给其他建议

**10. Retro（复盘）**
- Retro 必须包含失败模式、实际交付 vs 最初意图、做对了什么、做错了什么
- 禁止写空模板（全是占位符）
- 每个 done spec 必须有 retro，否则 `vibe next` 会阻止推进新 spec

### 全局约束

- 状态与证据存储在 `.agents/` 目录下
- 使用 `vibe` CLI 或 `vibe.py` 推进工作项状态
- **阶段推进必须先执行 `vibe next` 确认门禁**，推进后必须执行 `vibe status` 汇报进度
- 不得静默跳过状态转换
- 如果 spec 涉及 fallback、TTL/过期、跨组件链路或前端 state-changing 请求，Agent 必须先检查 `.agents/rules/testing.md` 是否已定义对应验证方式；未定义时，不得直接宣称验证完成
- 当用户说 `Vibe 复盘这个问题` 时，Agent 必须在当前项目内执行一次复盘：优先更新本项目的规则、文档、retro、testing 策略；仅把抽象后的治理结论作为 Skill 升级候选
- 当 Agent 发现 Skill 升级候选时，可以主动询问 `发现 N 条可能的 Skill 治理升级候选，是否应用？`，但在用户明确确认前，不得修改 Skill 核心
- 如果项目规则与 Skill 默认规则冲突，项目规则优先，但必须记录冲突原因

## 项目级治理建议（参考 — 不强制，按需采纳）

> 以下建议来自 Skill 升级评审中被判定为"项目级"的治理点。
> 它们不强制，但能显著提升项目质量。按需采纳到项目 AGENTS.md 或 .agents/rules/ 中。

### 候选提案规范

- **写候选时必须附 PoC 数据**：任何 `.agents/skill-upgrade-candidates/` 下的提案文件，必须包含实测数据（触发次数、影响范围、边界 case），不能只写"理论上应该这么检查"。没有数据的提案容易被拒绝。
- **单条优于打包**：一次提 1 条候选比打包提 8 条接受率高。聚焦 + 数据 > 广泛 + 猜测。
- **区分 Skill 级 vs 项目级**：提案必须明确标注是 Skill 级（跨项目通用）还是项目级（本项目特定）。Skill 级不含项目业务知识。

### Bug 治理

- **修复前必读完整治理文件**：修 bug 前不要只看 bug-inbox，还要读 BUG_INDEX.md、STATUS.md、CHANGELOG.md 等（如果项目有这些文件）。避免基于不完整信息选错 bug 或漏看根因。
- **修复范围必须声明**：type=bug 的 spec 必须有 `## 修复范围 (Fix Scope)` 段，声明已修复位置 + 故意不改的相邻位置 + 判断依据。
- **override_approver 不是 self-override**：如果 solo-session 必须走 override，指定一个 future session ID 作为 reviewer，不能"我自己 override 我自己"。

### 代码质量

- **diff 审查必须认真阅读代码**：`vibe commit` step 1 展示 diff 后，必须逐行检查是否有意外修改、scope creep、逻辑回归。不能只看 stat 就加 `--reviewed`。
- **改代码必须检查所有调用点**：修改函数签名/行为后，必须 grep 所有调用点，不能口头声称"已检查"。
- **bug fix 必须有双向证据**：fix 后 PASS + fix 前 FAIL，缺一不可。只有 PASS 证据 = fix 可能无效。

### Retro 质量

- **Retro 必须包含失败模式标签**：每个 retro 必须引用至少一个 failure mode label（Rule 25 taxonomy），不能只写现象不归类。
- **Retro action items 必须有终端状态**：`[ ]` 空项不能跨多个 retro 周期不关闭。必须推进到 `[active: rule-id]`、`[deferred: reason]` 或 `[superseded: other-id]`。

### 流程纪律

- **Done 后必须写 Retro**：spec 到达 done 后不能跳过 retro。`vibe next` 会强制推荐先写 retro。
- **Governance batch 允许但必须声明根因**：单根因的 governance batch（如 auto-refresh 70 plans）允许，但 commit message 必须声明根因 + review-summary 解释。
- **禁止多 spec 聚合 commit**：一次 commit 涉及多个 spec + 所有 evidence = 隐藏幽灵 spec，违反 R8.46。

### Session 启动 SOP

- 新 session 必做（不可跳）：先 `vibe status <project_root>` 看当前状态，再 `vibe next` 看下一步建议，再 `git status --short` 看本地改动
- 检查 `.agents/.skill-version` 是否与 Skill 版本一致，不同步时跑 `vibe upgrade`
- 检查 `.agents/skill-upgrade-candidates/` 是否有待处理候选

### `--quick` 使用边界

- `--quick` 仅用于纯文档改动（typo、格式调整）和 governance 资产变动（retro、规则、候选 sync）
- `--quick` 禁用于业务代码改动、bug fix、feature implement — 这些必须走完整 review + verify 流程
- 如果不确定该不该用 `--quick`，就不用

### 批量 Commit 边界

- Governance batch（多个 plans/rules/retros 同步）允许，但 commit message 必须声明单一根因（如"workflow.json 变更触发 70 plan digest refresh"）
- 业务代码 batch（多 spec + 各自 evidence 合并 1 commit）禁止 — 隐藏幽灵 spec
- 测试 fixture batch 可以合（同一根因的测试添加），不同根因必须拆

### Override Approver 身份（单 Actor 项目参考）

- Solo-session 项目如果必须走 override_approver，指定一个 future session ID 作为 reviewer，不能"我自己 override 我自己"
- Future session 起来后必须读原 spec/evidence/commit 才能 approve 或 reject
- 多 actor 项目不需要此规则


## 技术栈

- **语言/运行时**: {{LANGUAGE_RUNTIME}}
- **框架**: {{FRAMEWORK}}
- **数据库**: {{DATABASE}}
- **部署**: {{DEPLOYMENT}}

## 项目结构

```
{{PROJECT_STRUCTURE}}
```

## 编码约定

- 命名规范: {{NAMING_CONVENTION}}
- 格式化: {{FORMATTER}}
- 包管理: {{PACKAGE_MANAGER}}
- 测试框架: {{TEST_FRAMEWORK}}
- Git 分支策略: {{GIT_STRATEGY}}

## 架构约束

- {{ARCHITECTURE_CONSTRAINT_1}}
- {{ARCHITECTURE_CONSTRAINT_2}}
- {{ARCHITECTURE_CONSTRAINT_3}}

## 安全要求

- {{SECURITY_REQUIREMENT_1}}
- {{SECURITY_REQUIREMENT_2}}

## 不让 Agent 做的事

- {{DO_NOT_DO_1}}
- {{DO_NOT_DO_2}}
- {{DO_NOT_DO_3}}

## 当前状态

- 当前阶段: {{CURRENT_PHASE}}
- 最后更新: {{LAST_UPDATED}}
