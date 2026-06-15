# debugger-auxiliary — 实施计划

> 基于规格: .agents/specs/debugger-auxiliary.md | 规格摘要: a2a9cc160b22c2e9 | 上下文摘要: 356a554c668bdced | 生成: 2026-06-14 09:59 UTC

## 前置检查

- [ ] 规格已确认，无歧义
- [ ] 约束清晰，边界明确
- [ ] 依赖已就绪

## 任务列表

### Phase 1: 核心实现
- [ ] 实现核心逻辑（涉及 `vibe-coding-debugger/SKILL.md`、`vibe-coding-debugger/scripts/record_reproduction.py`、`vibe-coding-debugger/agents/openai.yaml`）
- [ ] 编写单元测试

### Phase 2: 集成与边界
- [ ] 修改现有代码集成（涉及 `vibe-coding-skill/scripts/doctor_project.py`（`KNOWN_AUXILIARIES` 加 `vibe-coding-debugger`）、`vibe-coding-skill/scripts/install_auxiliary.py`（无需改：自动发现 `vibe-coding-*` 兄弟）、`vibe-coding-skill/tests/test_workflow.py`（+4 测试））
- [ ] 编写集成测试（覆盖 5 条验收标准）

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
