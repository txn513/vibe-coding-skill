# {{PROJECT_NAME}}

{{PROJECT_DESCRIPTION}}

## Vibe Coding 治理

**本项目由 Vibe Coding Skill 治理。任何功能、缺陷、重构、交付问题或项目状态查询，
都必须通过 Vibe Coding 工作流处理。** 不要跳过 Spec → Verify → Review 门禁。

- 状态与证据存储在 `.agents/` 目录下
- 使用 `vibe` CLI 或 `vibe.py` 推进工作项状态
- 修复 Bug 前必须先复现并记录 reproduction 证据
- 高风险变更需要观察（observe）证据才能标记完成
- 如果 spec 涉及 fallback、TTL/过期、跨组件链路或前端 state-changing 请求，Agent 必须先检查 `.agents/rules/testing.md` 是否已定义对应验证方式；未定义时，不得直接宣称验证完成
- 当用户说 `Vibe 复盘这个问题` 时，Agent 必须在当前项目内执行一次复盘：优先更新本项目的规则、文档、retro、testing 策略；仅把抽象后的治理结论作为 Skill 升级候选
- 当 Agent 发现 Skill 升级候选时，可以主动询问 `发现 N 条可能的 Skill 治理升级候选，是否应用？`，但在用户明确确认前，不得修改 Skill 核心
- **阶段推进必须经过 Skill 门禁**：每次推进状态前，必须先执行 `vibe next` 确认门禁是否满足；推进后，必须执行 `vibe status` 汇报当前进度。不得静默跳过状态转换

---

## 阶段强制规范（Phase Gates）

**你必须严格遵守以下阶段顺序，除非满足「允许跳过条件」。
如果 `vibe next` 提示你跳过某个阶段，你必须先确认是否满足跳过条件；
不满足时，拒绝跳过并执行该阶段。**

### 阶段总览

```
Discover → Spec → Plan → Execute → Verify → Review → Release → Observe → Done
```

| 阶段 | 核心检查点 | 最常跳过 | 防护机制 |
|-----|----------|---------|---------|
| Discover | 需求记录 + 风险评级 | 直接写代码 | `vibe next` 检查 spec 存在性 |
| Spec | AC + Scope + Call Sites | 无 Spec 直接编码 | `validate_spec.py` 门禁 |
| Plan | 任务拆分 + 依赖标注 | 一次改太多 | `advance` 检查 plan 存在性 |
| Execute | Commit + Diff 审查 | 跳过 review | `--reviewed` 强制 + marker 文件 |
| Verify | 每条 AC 有证据 | 只有后端测试 | `verify` 检查 evidence 完整性 |
| Review | 独立 Reviewer | 自己审自己 | `reviewer != builder` 检查 |
| Release | 回滚方案 | 直接上线 | 手动确认 |
| Observe | 监控指标 | 不观察 | 项目级规则 |
| Done | 所有检查点通过 | 提前标记 done | `advance` 最终门禁 |

---

### 1. Discover（需求发现）

**强制完成：**
- [ ] 需求来源已记录（用户口述 / 文档 / 截图 / 链接）
- [ ] 需求类型已分类（feature / bug / refactor / chore）
- [ ] 风险等级已评估（low / medium / high）
- [ ] 至少一条验收标准已草拟（即使后续会细化）

**允许跳过：**
- 纯文档修改（typo、格式调整）→ 直接跳到 Execute
- 已存在 Intent 文档的 follow-up → 引用原 Intent，跳过 Discover

**禁止跳过：**
- ❌ 无记录的需求直接进入 Spec
- ❌ 未评估风险等级

---

### 2. Spec（规格定义）

**强制完成：**
- [ ] Spec 文件已创建（`.agents/specs/<id>.md`）
- [ ] Frontmatter 完整（Status / Risk / Type / Prompt version）
- [ ] 意图（Intent）已清晰描述「要解决什么问题」
- [ ] 验收标准（Acceptance Criteria）≥ 1 条，每条可独立验证
- [ ] 涉及范围（Scope）已界定，明确「做什么」和「不做什么」
- [ ] 如果修改现有类/函数：调用点（Call Sites）已 grep 并分类
- [ ] 如果 high-risk：security.md / testing.md 已检查

**允许跳过：**
- 纯文档修改 → 简化 Spec（只写 Intent + AC）
- Bug fix → 复现步骤 + 修复范围 即可

**禁止跳过：**
- ❌ 无 Spec 直接进入 Plan/Execute
- ❌ 无验收标准
- ❌ 无涉及范围（导致范围蔓延）

---

### 3. Plan（实施计划）

**强制完成：**
- [ ] Plan 文件已创建（`.agents/plans/<spec-id>.md`）
- [ ] 任务已拆分为可独立执行的子任务
- [ ] 每个子任务有明确的完成标准
- [ ] 依赖关系已标注（哪些任务必须先完成）

**允许跳过：**
- Low-risk + 任务简单（< 2 小时）→ 直接在 Spec 中写「实施步骤」，不单独出 Plan
- 已存在类似 Plan → 复用并标注差异

**禁止跳过：**
- ❌ High/Medium-risk 无 Plan 直接编码
- ❌ 任务未拆分（导致一次改动过大）

---

### 4. Execute（编码实施）

**强制完成：**
- [ ] 每次代码变更前 `vibe commit`（或至少 `git commit`）
- [ ] Commit 前 diff 已审查（Rule 53）
- [ ] 如果修改调用点：相邻位置保护性测试已检查（Rule 56）
- [ ] 代码变更范围与 Spec 一致（无范围蔓延）

**允许跳过：**
- 纯文档修改 → `vibe commit --quick`
- 紧急修复 → `vibe commit --no-verify`（需记录原因到 `.agents/commit-skip-log.md`）

**禁止跳过：**
- ❌ 未 commit 就继续下一步
- ❌ 未审查 diff 就 commit
- ❌ 代码变更超出 Spec 范围（未走 Spec 变更流程）

---

### 5. Verify（验证）

**强制完成：**
- [ ] 验证证据已记录（`.agents/evidence/<spec-id>/`）
- [ ] 每条 AC 都有对应的验证证据
- [ ] 如果 type=bug：双向验证（fix 前 FAIL + fix 后 PASS）
- [ ] 如果涉及 UI：截图 / Live HTTP 交互证据
- [ ] 降级链路测试（如果涉及多级 fallback）
- [ ] 时序状态模拟（如果涉及缓存/TTL/过期）

**允许跳过：**
- 纯文档修改 → 手动确认即可
- Low-risk + 已有自动化测试覆盖 → 简化验证

**禁止跳过：**
- ❌ 无验证证据就标记 done
- ❌ 只有后端测试无 UI 验证（如果 AC 涉及 UI）
- ❌ Bug fix 只有「fix 后 PASS」无「fix 前 FAIL」

---

### 6. Review（审查）

**强制完成：**
- [ ] Reviewer 与 Builder 不同身份（Rule 5）
- [ ] Review 文档已创建（`.agents/reviews/<spec-id>.md`）
- [ ] 独立 grep 调用点（Rule 59）
- [ ] 如果 high-risk：独立 Agent / Session 审查

**允许跳过：**
- Low-risk + 单人项目 → 自我审查，但需记录原因到 `.agents/reviews/<spec-id>.md`
- 纯文档修改 → 简化审查

**禁止跳过：**
- ❌ High/Medium-risk 无独立 Review
- ❌ Reviewer 与 Builder 同一身份（未声明原因）

---

### 7. Release（发布）

**强制完成：**
- [ ] 版本号已更新（如果项目有 VERSION 文件）
- [ ] Changelog 已记录
- [ ] 回滚方案已准备

**允许跳过：**
- 未上线项目 → 标记为 done 即可
- 内部工具 → 简化发布流程

**禁止跳过：**
- ❌ 无回滚方案直接上线

---

### 8. Observe（观察）

**强制完成：**
- [ ] 监控指标已确认（如果有）
- [ ] 用户反馈渠道已准备

**允许跳过：**
- 内部工具 → 简化观察

**禁止跳过：**
- ❌ 无监控直接标记 done

---

### 9. Done（完成）

**强制完成：**
- [ ] 所有 AC 已验证
- [ ] 所有证据已归档
- [ ] Retro 已写（如果项目要求）

**允许跳过：**
- 无

**禁止跳过：**
- ❌ 未完成 Verify 就标记 done
- ❌ 未完成 Review 就标记 released

---

## 防跳过核心原则

### 1. 无 Spec 不编码

任何代码变更必须有对应的 Spec 文件。如果用户说「改个小东西」，你必须：
1. 确认是否满足「允许跳过 Spec」的条件
2. 如果不满足，先写 Spec（哪怕只有 Intent + AC）
3. 如果满足，记录跳过原因到 `.agents/skip-log.md`

### 2. 无 Plan 不实施

High/Medium-risk 必须有 Plan。如果用户催促「先写代码」，你必须：
1. 评估风险等级
2. 如果 high/medium，坚持先出 Plan
3. 如果 low 且简单，可以在 Spec 中写实施步骤，不单独出 Plan

### 3. 无 Review 不提交

Commit 必须审查 diff（Rule 53）。两步操作：
1. `vibe commit`（不带 `--reviewed`）→ 看 diff
2. `vibe commit --reviewed --review-summary '...'` → 提交

禁止：
- 直接 `git commit` 绕过 vibe
- 连续使用 `--quick` 或 `--no-verify` 不记录原因
- Review summary 写套话（如「确认无误」）

### 4. 无 Verify 不 Done

每条 AC 必须有验证证据。禁止：
- 只有后端测试无 UI 验证（如果 AC 涉及 UI）
- Bug fix 只有「fix 后 PASS」无「fix 前 FAIL」
- 标记 done 时 evidence 目录为空

### 5. 无独立 Review 不 Release

Medium/High-risk 必须独立 Reviewer。禁止：
- 自己审自己（未声明原因）
- Reviewer 与 Builder 同一 Session

---

## 跳过记录模板

如果必须跳过某个阶段，记录到 `.agents/skip-log.md`：

```markdown
## 跳过记录

### 2026-07-06
- **跳过阶段**: Plan
- **Spec ID**: fix-typo-login-page
- **原因**: 纯文档修改（typo），low-risk
- **替代措施**: 直接在 Spec 中写实施步骤
- **确认人**: Agent
```

---

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
