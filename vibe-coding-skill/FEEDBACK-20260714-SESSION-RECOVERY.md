# 反馈给项目 Agent — Session 恢复 & 断点续传 (2026-07-14)

## ✅ 已完成：Session-State Advisory (commit 84b0f51)

**改动**:
- `scripts/project_status.py` 新增 `_last_activity_timestamp()` — 解析 `.agents/activity.md` 获取最后活动时间
- `recommend_next()` 顶部加 session-state advisory：距离上次 activity >30 分钟时，自动打印：
  ```
  🧠 Session 状态提示：距离上次 activity 已 X 分钟。
     如果这是新 session，请先运行 `vibe status` 恢复状态 (Rule 66)。
  ```
- 32 个 next 相关测试通过

**触发条件**:
- `.agents/activity.md` 存在且最后一条记录时间 >30 分钟
- 如果 activity.md 为空或不存在，不触发（新项目或从未推进过）

---

## ✅ 已完成：Rule 66 (commit 29d9642)

**SKILL.md Rule 66**: "Session recovery: Agent MUST re-read project state after context loss"
- 任何平台（Codex / Claude Code / Cursor 等）的 Agent 在会话中断后，必须先运行 `vibe status` + `vibe next` 恢复状态
- `.agents/` 目录是唯一可信的状态源；Agent 内存不可信

**templates/agents.md "Session 恢复与断点续传"节**:
- 会话中断后必须先恢复状态再工作
- 恢复后核对当前激活 spec、阶段、未完成项
- 禁止凭记忆假设，每次 session 恢复必须重新读取治理文件

---

## Agent 使用方式

**新 session / 对话被 compact 后**:
1. 先运行 `vibe status` — 恢复项目当前状态
2. 再运行 `vibe next` — 获取下一步建议（会自动检测是否需要恢复）
3. 简报当前状态给用户，确认后再继续

**不需要手动操作**:
- `vibe next` 会自动检测并提示（如果 activity >30 分钟）
- 不需要额外安装或配置

---

## Skill 版本信息

- **当前 HEAD**: `84b0f51` (session-state-advisory)
- **安装路径**: `~/.pi/agent/skills/vibe-coding`
- **生效方式**: 已软链接，无需重新安装
