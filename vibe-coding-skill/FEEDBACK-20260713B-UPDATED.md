# 反馈给项目 Agent — Skill 升级候选评估结果 (20260713b 更新版)

## ✅ 候选 1 — 已采纳并落地 (commit 62603de)

**标题**: doctor parser 接受 `无影响` / `no-impact` 关键字 (Rule 57)

**修复内容**:
- `scripts/doctor_project.py:150` — `impact_types` 从 6 个扩展到 10 个
- 新增回归测试 `test_doctor_accepts_no_impact_keyword`

---

## ❌ 候选 2 — 暂缓，不采纳

**标题**: R-D-6 reconcile 加 commit gate 强制

**不采纳理由**: 与 20260712b 同根，已拒绝。commit 前 reconcile 5 步 SOP 阻塞开发流程。

---

## ✅ 候选 3 — 已采纳并落地 (commit bcb851e)

**标题**: doctor-retrofit 工具跨项目通用 — 批量 Rule 56/57 合规

**来源**: 妙藏项目实测 (188 specs → 66 待改 → warnings 从 140 降到 41)

**新增文件**:
- `scripts/doctor_retrofit.py` (11.8KB) — 批量 retrofit 工具
- `scripts/vibe.py` — 新增 `vibe doctor-retrofit` 子命令

**功能**:
- 扫描 `.agents/specs/*.md` 中 status=done 的 spec
- 自动添加 Rule 57 表格 (受影响的读路径)
- 自动添加 Rule 56 风险已知晓表格 (故意不改的相邻位置)
- 在 不动文件 行追加 `(无新增/无修改/无删除)` 关键字
- dry-run 默认，加 `--apply` 才实际修改
- 自动刷新 plan digests (`--no-plan-refresh` 可跳过)
- 幂等：已合规的 spec 自动跳过

**使用方式**:
```bash
# 预览 (dry-run)
vibe doctor-retrofit /path/to/project

# 实际修改
vibe doctor-retrofit /path/to/project --apply

# 只处理某个 spec
vibe doctor-retrofit /path/to/project --spec my-spec --apply
```

**你方动作**:
1. 归档 `skill-upgrade-candidate-20260713b.md`
2. 头部追加：`状态: 部分采纳 (候选1: commit 62603de; 候选3: commit bcb851e; 候选2暂缓)`

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

---

## Skill 版本信息

- **当前 HEAD**: `bcb851e` (doctor-retrofit)
- **安装路径**: `~/.pi/agent/skills/vibe-coding`
