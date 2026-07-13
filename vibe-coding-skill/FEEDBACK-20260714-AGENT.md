# 反馈给项目 Agent — Skill 升级候选评估结果 (20260712b + 20260712c + 20260713)

## ✅ 20260712c — 已采纳并落地 (commit c6b358c)

**标题**: propose_skill_upgrade suffix regex bug — 防止同日提案互相覆盖

**修复内容**:
- `scripts/propose_skill_upgrade.py:36` — 修复 raw-string regex：`rf"...\\.md$"` → `rf"...\.md$"`
  - 原 bug：`\\.md` 在 raw string 中是"字面反斜杠 + 任意字符"，永远不匹配 `.md` 后缀
  - 结果：`_find_next_suffix()` 返回空字符串，同日第二份提案覆盖第一份
- `propose_skill_upgrade()` — 文件存在时从 `print + return` 改为 `raise FileExistsError`
  - 消除 silent overwrite，调用方必须显式处理冲突
- 新增回归测试 `test_propose_skill_upgrade_same_day_no_overwrite` (73 个相关测试全部通过)

**你方动作**:
1. 将 `.agents/skill-upgrade-candidates/skill-upgrade-candidate-20260712c.md` 归档到 `.agents/archive/skill-upgrade-candidates/`
2. 归档前在文件头部追加：`状态: 已采纳 (commit c6b358c)`

---

## ✅ 20260712b — 已采纳并落地 (commit aa51bd7)

**标题**: R-Lighter-Governance-Gate — 纯治理类 commit 跳过 per-file line-ref 要求

**修复内容**:
- `scripts/commit.py` 新增 `_is_governance_file(filepath)` + `_all_changed_are_governance(project_root, changed_files)`
  - 治理类文件定义：`.md` / `.txt` / `.json` / `.yml` / `.yaml` / `.toml` / `.gitignore` 等
  - 目录匹配：`.agents/rules/` / `.agents/retros/` / `docs/` 下的文件
- line-ref gate 前加 governance-only 分支：
  - 当 **所有** 变更文件都是治理类时，跳过 per-file 行号引用要求
  - missing_file gate（每个文件被 review-summary 提及）仍然保留
  - 生产代码 commit（`.py` / `.sh` / `.js` 等）不受影响，仍走 full gate
- 新增回归测试 `test_commit_governance_only_skips_line_ref_gate` (79 个 commit 相关测试全部通过)

**你方动作**:
1. 将 `.agents/skill-upgrade-candidates/skill-upgrade-candidate-20260712b.md` 归档到 `.agents/archive/skill-upgrade-candidates/`
2. 归档前在文件头部追加：`状态: 已采纳 (commit aa51bd7)`

---

## ⏳ 20260713 — 候选1 和 候选3 状态

**候选1 (Single-Actor Gate Skip)**: 部分已做
- 2026-07-08c 已有 `override_approver` bypass（`set_status.py:603-624`）
- 剩余 identity check 优化（`_identity_matches` 在空 role 时的处理）可做但优先级降低
- 状态：**暂缓**，等后续 retro 中再次遇到再评估

**候选3 (Chinese i18n Partition)**: 未复现
- `partition(':')` 中文误切场景未在测试中复现
- `20260713.md` 中提到的案例（`skills.py:1160 hint` 等）实际测试通过
- 状态：**暂不处理**，如有具体复现步骤再重新评估

---

## Skill 版本信息

- **当前 Skill HEAD**: `aa51bd7` (governance-lighter-gate)
- **安装路径**: `~/.pi/agent/skills/vibe-coding`
- **生效方式**: 已软链接，无需重新安装
- **测试状态**: 79 个 commit 相关测试全部通过

---

## 📋 Skill 级别提案文档规范

**产生提案时**:
- **存放路径**: `<project_root>/.agents/skill-upgrade-candidates/skill-upgrade-candidate-YYYYMMDD<N>.md`
- **命名规则**: `skill-upgrade-candidate-YYYYMMDD.md` → 若同日已有，自动加后缀 `b`, `c`, `d`...

**归档时**:
- 将文件从 `.agents/skill-upgrade-candidates/` 移到 `.agents/archive/skill-upgrade-candidates/`
- 在文件头部追加 `状态: 已采纳 / 已拒绝 / 已归档 (commit hash)`
- **必须给出完整文档地址**，方便管理员追溯和评审
