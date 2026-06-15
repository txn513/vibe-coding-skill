# changelog-auto-on-release — 实施计划

> 基于规格: .agents/specs/changelog-auto-on-release.md | 规格摘要: c1992d10d9de6100 | 上下文摘要: 356a554c668bdced | 生成: 2026-06-14 09:52 UTC

## 前置检查

- [ ] 规格已确认，无歧义
- [ ] 约束清晰，边界明确
- [ ] 依赖已就绪

## 任务列表

### Phase 1: 核心实现
- [ ] 实现核心逻辑（涉及 无）
- [ ] 编写单元测试

### Phase 2: 集成与边界
- [ ] 修改现有代码集成（涉及 `vibe-coding-skill/scripts/set_status.py`（+25 行：新增 `changelog_version` / `auto_changelog` 参数 + released 分支末尾调用）、`vibe-coding-skill/scripts/vibe.py`（+10 行：advance 子命令新增 `--changelog-version` 与 `--skip-changelog` 参数，转发给 set_status）、`vibe-coding-skill/tests/test_workflow.py`（+80 行：3-4 个新测试）、`vibe-cli/src/main.py`（+8 行：转发新参数））
- [ ] 编写集成测试（覆盖 3 条验收标准）

### Phase 3: 验证与收尾
- [ ] 手动验收测试
- [ ] Code Review（独立 Agent 审查）

## 验证门禁

每个 Phase 完成后必须通过:
- [ ] 项目定义的自动检查通过
- [ ] 与本阶段相关的行为验证通过
- [ ] 所需证据已记录

## 风险点

- （从规格中识别风险）
- （从规格中识别风险）
