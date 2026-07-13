# 反馈给项目 Agent — Skill 升级候选评估结果 (20260712b + 20260712c)

## ✅ 20260712c — 已采纳并落地

**标题**: propose_skill_upgrade suffix regex bug — 防止同日提案互相覆盖

**状态**: 已合并到 Skill 核心 (commit `c6b358c`)

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

## ❌ 20260712b — 暂缓，不采纳

**标题**: R-Pre-Next-Action-Reconcile — Agent 输出 next-action 前必须先 reconcile 治理资产

**不采纳理由** (4 条):
1. **无硬门禁绑定** — 8 步 SOP 仅靠 Agent 自觉执行，vibe next 不会自动触发，Agent 可合法跳过
2. **功能重叠** — vibe next 已在 recommendation 前自动跑 doctor，已覆盖 retro active items / pending proposals / status drift
3. **执行负担 > 收益** — 8 步 grep 依赖路径硬编码，不同项目目录结构不同，不适合作为通用 Skill 规则
4. **项目级已替代** — 妙藏 Gemkeep 的 `.agents/rules/dev.md` R-D-6 已覆盖此需求

**你方动作**:
1. `skill-upgrade-candidate-20260712b.md` 归档到 `.agents/archive/skill-upgrade-candidates/`
2. 归档前在文件头部追加：`状态: 已拒绝 (理由: 无硬门禁绑定 + 功能重叠 + 执行负担过高)`

---

## Skill 版本信息

- **当前 Skill HEAD**: `c6b358c` (15d218b-fix-suffix-regex-same-day-overwrite)
- **安装路径**: `~/.pi/agent/skills/vibe-coding`
- **生效方式**: 已软链接，无需重新安装

---

## 📋 Skill 级别提案文档规范

**产生提案时**:
- **存放路径**: `<project_root>/.agents/skill-upgrade-candidates/skill-upgrade-candidate-YYYYMMDD<N>.md`
  - 如: `/Users/lance/Documents/trae_projects/社交媒体收藏夹工具/.agents/skill-upgrade-candidates/skill-upgrade-candidate-20260712c.md`
- **命名规则**: `skill-upgrade-candidate-YYYYMMDD.md` → 若同日已有，自动加后缀 `b`, `c`, `d`...
- **完整文档地址示例**:
  - 原始: `/Users/lance/Documents/trae_projects/社交媒体收藏夹工具/.agents/skill-upgrade-candidates/skill-upgrade-candidate-20260712c.md`
  - 归档: `/Users/lance/Documents/trae_projects/社交媒体收藏夹工具/.agents/archive/skill-upgrade-candidates/skill-upgrade-candidate-20260712c.md`

**归档时**:
- 将文件从 `.agents/skill-upgrade-candidates/` 移到 `.agents/archive/skill-upgrade-candidates/`
- 在文件头部追加 `状态: 已采纳 / 已拒绝 / 已归档 (commit hash)`
- **必须给出完整文档地址**，方便管理员追溯和评审
