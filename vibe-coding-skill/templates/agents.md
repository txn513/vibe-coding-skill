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
- 如果能定位到具体 spec 或 bug，优先执行 `vibe retrospective <spec_name>`；如果无法定位，只询问缺少的 spec / bug 名称
- 当 Agent 发现 Skill 升级候选时，可以主动询问 `发现 N 条可能的 Skill 治理升级候选，是否应用？`，但在用户明确确认前，不得修改 Skill 核心
- **阶段推进必须经过 Skill 门禁**：每次推进状态前，必须先执行 `vibe next` 确认门禁是否满足；推进后，必须执行 `vibe status` 汇报当前进度。不得静默跳过状态转换

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
