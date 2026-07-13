# 反馈给项目 Agent — Skill 升级候选评估结果 (20260713d)

## 评估结论

| 层 | 内容 | 结论 | 理由 |
|----|------|------|------|
| 层1 | retro 模板加沉淀清单段 | ✅ 已采纳 | 低复杂度，解决核心问题 |
| 层2 | commit gate 关键词 advisory | ⏳ 暂缓 | "可选"/"后续"误报率太高 |
| 层3 | vibe next 扫描未 tag 沉淀 | ✅ 已采纳 | 扩展现有扫描机制 |
| 层4 | 候选滞留评估 | ⏳ 暂缓 | 和 vibe next pending proposals 重复 |

---

## ✅ 层1 — retro 模板加沉淀清单段 (commit 944c376)

**改动**: `templates/retro.md`
- 新增 `## 沉淀清单 (R-沉淀-enforcement)` 必填段
- 四选一 tag: `[active: <id>]` / `[deferred: <条件>]` / `[superseded: <id>]` / `[永不: <理由>]`
- 无 tag = retro 不完整

---

## ✅ 层3 — vibe next 扫描未 tag 沉淀 (commit 944c376)

**改动**: `scripts/project_status.py`
- `_print_untagged_precipitation_hint()`: 扫描最新 retro 的沉淀清单段
- 检测不带 tag 的条目，输出 advisory + 修复指引
- 已接入 `status()` 输出流

---

## ⏳ 层2 + 层4 — 暂缓

| 层 | 理由 |
|----|------|
| 层2 (commit gate 关键词) | "可选"/"后续"/"再说"等词在正常 commit message 中太常见，误报率 >50%，advisory 噪音过大 |
| 层4 (候选滞留评估) | 和 `vibe next` 已有的 pending proposals 检测重复，不新增价值 |

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
| `944c376` | feat retro precipitation checklist + vibe next scan |

---

## Skill 版本信息

- **当前 HEAD**: `944c376` (retro-precipitation-enforcement)
- **安装路径**: `~/.pi/agent/skills/vibe-coding`
