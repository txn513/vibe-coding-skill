# Skill 升级反馈 — 2026-07-13

## 20260712c ✅ 已采纳并落地 (commit c6b358c)

**标题**: propose_skill_upgrade suffix regex bug — 防止同日提案互相覆盖

**改动**:
1. `scripts/propose_skill_upgrade.py:36` — 修复 `rf"...\\.md$"` → `rf"...\.md$"` (raw string 中 `\\.md` 是字面反斜杠 + 任意字符，永远不匹配真实 `.md` 后缀)
2. `propose_skill_upgrade()` — 文件存在时从 `print + return filepath` 改为 `raise FileExistsError`，强制调用方处理冲突，消除 silent overwrite
3. `tests/test_workflow.py` — 新增回归测试 `test_propose_skill_upgrade_same_day_no_overwrite`

**测试**: 73 个 propose/status/next/doctor 相关测试全部通过，新增同日多提案 test 通过。

---

## 20260712b ❌ 暂缓，不采纳

**标题**: R-Pre-Next-Action-Reconcile — Agent 输出 next-action 前必须先 reconcile 治理资产

**理由**:
1. 没有硬门禁绑定 — vibe next 不会自动执行 8 步 reconcile SOP，Agent 可以合法跳过
2. 功能重叠 — vibe next 已在 recommendation 前自动跑 doctor，已覆盖 retro active items / pending proposals / status drift 的自动检测
3. 执行负担 > 收益 — 8 步 SOP 步骤多、grep 依赖路径硬编码，不适合作为通用 Skill 规则
4. **项目级可替代** — 妙藏 Gemkeep 已在 `.agents/rules/dev.md` R-D-6 落地项目级 reconcile 规则，满足需求

**建议**: 项目级 `dev.md` R-D-6 已足够，Skill 级暂不增加此规则。后续 retro 中如果反复出现"menu 漏报已记录 action item"，再重新评估。
