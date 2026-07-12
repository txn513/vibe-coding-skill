# Skill 升级候选 — Skill 升级提案标准化工作流

来源: 管理员直接提议（Lance）
日期: 2026-07-13
标题: 新增 vibe propose-skill-upgrade 命令 + 提案标准化
状态: **已采纳**

---

## 候选：Skill 升级候选提案标准化工作流（governance 级）

**问题**：Agent 不知道把跨项目的治理改进写到哪，导致 retro 里提了很多 Skill 候选但没有统一归档。管理员评审时散落在各个 retro 中。

**建议方案**：
1. 新增 `vibe propose-skill-upgrade <project> "<标题>"` 命令
2. 自动在 `.agents/skill-upgrade-candidates/` 创建结构化提案（含模板）
3. `vibe next` 自动检测未归档提案并输出 advisory
4. retro.md 模板更新，引导 Agent 写提案到指定目录
5. 管理员评审后归档到 `.agents/archive/skill-upgrade-candidates/`

**通用性审计**：
- ✅ 通用：所有 vibe-coding 项目
- ✅ 不含项目知识：纯工作流规范
- ✅ 跨项目适用：是
- 失败模式：rule exists, but no place to put it

**影响范围**：所有使用 vibe-coding 的 Agent 和管理员

**实施复杂度**：中

**预期收益**：统一 Skill 升级提案的收集、评审、归档流程

---

## 管理员反馈

### 状态：已采纳 ✅

- **实施 commit**: `365025e` — feat(skill): propose-skill-upgrade command + auto-detect pending proposals
- **实施日期**: 2026-07-13
- **测试覆盖**: 595 tests pass（新增 3 个 case）
