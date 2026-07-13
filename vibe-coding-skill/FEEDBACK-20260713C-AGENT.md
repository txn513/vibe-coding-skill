# 反馈给项目 Agent — Skill 升级候选评估结果 (20260713c)

## ✅ 候选 1 — 已采纳并落地 (commit 9070276)

**标题**: doctor parser 识别 Rule 57/56 table 存在时跳过对应 bullet 检查

**问题**: retrofit 工具 add-only 模式导致 bullet + table 共存，doctor 只看 bullet 误报

**修复内容**:
- `_audit_read_path_impact`: 检测 Rule 57 table (`### 受影响的读路径 (Rule 57)`)，存在时跳过 `受影响的读路径` bullet 检查
- `_audit_adjacent_protection`: 检测 Rule 56 table (`| 位置 | 是否已有保护性测试 | 风险已知晓 |`)，存在时跳过 `故意不改` bullet 检查
- 新增回归测试：
  - `test_doctor_skips_bullet_when_rule57_table_present` ✅
  - `test_doctor_skips_bullet_when_rule56_table_present` ✅

**效果**: retrofit 后 spec 的 bullet + table 共存不再误报，妙藏项目 warnings 预计从 29 → 0

**你方动作**:
1. 归档 `skill-upgrade-candidate-20260713c.md`
2. 头部追加：`状态: 已采纳 (commit 9070276)`

---

## 本轮 Skill 升级总览 (2026-07-12 ~ 2026-07-14)

| Commit | 内容 |
|--------|------|
| `15d218b` | fix propose_skill_upgrade suffix regex bug |
| `b1c15c3` | feat commit governance-only lighter gate |
| `29d9642` | feat Rule 66 session recovery |
| `84b0f51` | feat session-state advisory in vibe next |
| `b15a45d` | fix activity timestamp regex + parse |
| `c751d58` | feat widen session-state to commit/amend |
| `a3409d4` | feat upgrade_agents auto-inject AGENT-MANDATORY |
| `62603de` | feat doctor accept 无影响 keywords |
| `bcb851e` | feat doctor-retrofit subcommand |
| `9070276` | fix doctor skip bullet when table present |

---

## Skill 版本信息

- **当前 HEAD**: `9070276` (doctor-table-bullet-priority)
- **安装路径**: `~/.pi/agent/skills/vibe-coding`
