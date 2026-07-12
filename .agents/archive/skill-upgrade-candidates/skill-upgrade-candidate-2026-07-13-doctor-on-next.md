# Skill 升级候选 — vibe next 自动触发 doctor

来源: 2026-07-12 retro（fix-stream-dns-rebinding 流程反思）
日期: 2026-07-13
标题: vibe next 自动触发 vibe doctor（方案 A）
状态: **已采纳**

---

## 候选：vibe next 自动触发 doctor（governance 级）

**问题**：Agent 容易跳过 `vibe doctor`，导致 workflow violation 被忽视。

**建议方案**：
- `vibe next` 输出推荐前自动运行 `vibe doctor`
- 结果缓存 60 秒避免重复
- 支持 `VIBE_QUIET_AUTO_DOCTOR=1` 静默模式

**通用性审计**：
- ✅ 通用：所有 vibe-coding 项目都使用 `vibe next`
- ✅ 不含项目知识：纯 doctor 集成
- ✅ 跨项目适用：是
- 失败模式：rule exists, but agent skips silently

**影响范围**：所有运行 `vibe next` 的 Agent

**实施复杂度**：低

**预期收益**：防止 Agent 静默忽略 workflow violation

---

## 管理员反馈

### 状态：已采纳 ✅

- **实施 commit**: `a8bc97b` — feat(skill): auto-fire doctor on vibe next + fix commit-msg hook type
- **实施日期**: 2026-07-13
- **测试覆盖**: 592 tests pass
