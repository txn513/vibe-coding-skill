# 反馈给项目 Agent — Skill 升级候选评估结果 (20260713g)

## 评估结论

| 候选 | 内容 | 结论 | 理由 |
|------|------|------|------|
| 候选1 | spec amend / commit 后 auto-refresh plan digest | ✅ 已采纳 | 高通用性，根治 stale plan drift，实现简单可靠 |

---

## ✅ 候选1 — 已采纳 (commit e74b2e8)

**标题**: spec amend / commit 后 auto-refresh plan digest (R-plan-auto-refresh)

**改动**:

1. **`scripts/spec_amend.py`**: amend spec 完成后，自动检测 plan 文件是否存在，存在则静默调用 `--refresh-digest-only` 刷新 plan header 的 spec digest。
2. **`scripts/commit.py`**: commit 前（verify 通过后、git commit 前），自动检测本次 commit 包含的 spec 文件，对每个 spec 静默调用 `--refresh-digest-only` 刷新 plan digest。

**核心设计**:
- 自动检测: 不需 Agent 手动操作
- 静默执行: 不阻塞主流程（amend/commit），失败仅输出 warning
- 范围限定: 仅针对 `.agents/specs/*.md` 改动，排除 `-amendments.md`

**跟现有 `--refresh-digest-only` 的关系**:
- `generate_plan.py` 已提供 `refresh_plan_digests_only()` 函数
- 新 hook 复用现有 CLI `vibe plan --refresh-digest-only`，不引入新代码路径
- 如果 plan 不存在或老格式 → 跳过，不影响流程

---

## Skill 版本信息

- **当前 HEAD**: `e74b2e8` (auto-refresh plan digest)
- **安装路径**: `~/.pi/agent/skills/vibe-coding`
