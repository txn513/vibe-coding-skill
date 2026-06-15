# suite-auxiliary-onboarding — 实施计划

> 基于规格: .agents/specs/suite-auxiliary-onboarding.md | 规格摘要: d5cef4f2cd124c8a | 上下文摘要: 356a554c668bdced | 生成: 2026-06-14 09:29 UTC

## 前置检查

- [ ] 规格已确认，无歧义
- [ ] 约束清晰，边界明确
- [ ] 依赖已就绪

## 任务列表

### Phase 1: 核心实现
- [ ] 实现核心逻辑（涉及 `vibe-coding-skill/scripts/install_auxiliary.py`（≈ 200 行）、`vibe-coding-reviewer/agents/openai.yaml`（4 行））
- [ ] 编写单元测试

### Phase 2: 集成与边界
- [ ] 修改现有代码集成（涉及 `vibe-coding-skill/scripts/vibe.py`（+30 行）、`vibe-coding-skill/scripts/doctor_project.py`（+30 行）、`vibe-coding-skill/scripts/generate_review.py`（+5 行）、`vibe-coding-skill/SKILL.md`（+10 行）、`vibe-coding-skill/tests/test_workflow.py`（+150 行）、`vibe-cli/src/main.py`（+25 行）、`vibe-coding-reviewer/scripts/review_decision.py`（+10 行））
- [ ] 编写集成测试（覆盖 4 条验收标准）

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
