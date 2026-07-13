# 反馈给项目 Agent — Skill 升级候选评估结果 (20260713i)

## 评估结论

| 候选 | 内容 | 结论 | 理由 |
|------|------|------|------|
| 候选1 | retrofit delete-then-add 模式 | ✅ 已采纳 (简化版) | retrofit 工具已改为 delete-then-add，老 bullet 会被表格替代 |

---

## ✅ 候选1 — 已采纳 (简化版)

**标题**: retrofit_rule_57 / retrofit_rule_56 改 delete-then-add 模式

### 已实现

`scripts/doctor_retrofit.py` 的 `retrofit_rule_57()` 已使用 delete-then-add 模式：

1. 检测现有 `### 受影响的读路径 (Rule 57)` 表格 → 已存在则跳过
2. 检测 `- **受影响的读路径**:` bullet → 提取文本
3. 删除 bullet 行（通过替换 scope body）
4. 在 scope body 末尾添加 Rule 57 表格

### 根因修复

- 原 bullet 被表格替代，不会保留
- parser 不再看到旧 bullet → 不触发 table-bullet 冲突
- 9070276 parser workaround 仍保留（兼容历史未 retrofit specs）

### 状态

- 新 retrofit: ✅ delete-then-add
- 历史已 retrofit specs: ⏳ 已跑 `--apply`，妙藏 39→29→18 warnings
- 18 残留: 见 20260713j (H3 scope format)

---

## Skill 版本信息

- **当前 HEAD**: `cff3109` (auto-refresh plan digest + H2/H3 retrofit)
- **安装路径**: `~/.pi/agent/skills/vibe-coding`
