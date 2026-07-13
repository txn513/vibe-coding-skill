# 反馈给项目 Agent — Skill 升级候选评估结果 (20260713k)

## 评估结论

| 候选 | 内容 | 结论 | 理由 |
|------|------|------|------|
| 候选1 | plan format 强制 + auto-upgrade 老格式 | ✅ 已采纳 (简化版) | refresh-digest-only 检测到缺 digest 时自动 upgrade，不阻塞 |

---

## ✅ 候选1 — 已采纳 (commit 1bde830)

**标题**: plan file format 强制 + 老 format auto-upgrade

### 已实现

`scripts/generate_plan.py::refresh_plan_digests_only()` 已改：

**Before**: 检测不到 digest 行 → `⚠️  plan header 不含可识别的 digest 行 (老格式 plan); 未修改` → 跳过

**After**: 检测不到 digest 行 → 自动在 plan 第一行标题后插入 digest header → `✅ plan header 已自动升级 (老格式 → 新格式)` → 继续

```python
# 老格式 plan (无 digest header)
# Plan: xxx
## 任务拆分
...

# 新格式 plan (auto-upgraded)
# Plan: xxx
> 基于规格: .agents/specs/xxx.md | 规格摘要: <16hex> | 上下文摘要: <16hex> | 生成: <timestamp>
## 任务拆分
...
```

### 跟提案的差异

| 提案层 | 状态 | 说明 |
|--------|------|------|
| templates/plan.md 标记必填 | ⏸ 暂缓 | 模板已含 digest 行，老格式是历史问题 |
| generate_plan.py 创建时强制 digest | ✅ 已有 | 新 plan 自动生成 digest header |
| refresh-digest-only auto-upgrade | ✅ 已采纳 | 见 commit 1bde830 |
| vibe plan --migrate-format | ⏸ 暂缓 | auto-upgrade 在 refresh 时自动触发，不需要单独 CLI |

### 效果

- `vibe plan --refresh-digest-only` 遇到老格式 plan → 自动 upgrade，不再报错
- Doctor stale plan warning 中“老格式”类问题 → 根治
- 妙藏 doctor-retrofit-tool 等老 plan → 下次 refresh 自动升级

---

## Skill 版本信息

- **当前 HEAD**: `1bde830` (refresh-digest-only auto-upgrade)
- **安装路径**: `~/.pi/agent/skills/vibe-coding`
