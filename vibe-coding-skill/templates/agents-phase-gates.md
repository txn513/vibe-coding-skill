# {{PROJECT_NAME}}

{{PROJECT_DESCRIPTION}}

## Vibe Coding 治理（强制 — 每个环节不可跳过）

**本项目由 Vibe Coding Skill 治理。任何功能、缺陷、重构、交付问题或项目状态查询，都必须通过 Vibe Coding 工作流处理。**

### 流程顺序（不可逆，不可跳过）

Discovery → Spec → Plan → Execute → Verify → Review → Release → Observe → Done → Retro

每个阶段推进前，必须先完成当前阶段的所有门禁，否则不得 advance。

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
- **AGENTS.md 模板升级**: 运行 `vibe upgrade-agents /path/to/project --dry-run` 预览合并最新模板（保留用户内容）

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
