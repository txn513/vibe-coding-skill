# 反馈给项目 Agent — Skill 升级候选评估结果 (20260713h)

## 评估结论

| 候选 | 内容 | 结论 | 理由 |
|------|------|------|------|
| 候选1 | set_status / spec_amend frontmatter dedup | ⏳ 已覆盖 / 低优先级 | 当前工具已用 replace (非 append) 写入 frontmatter，新数据不会产生重复；历史重复需一次性 cleanup |

---

## ⏳ 候选1 — 已覆盖 / 低优先级

**标题**: set_status / confirm_risk / spec_amend 写入 frontmatter 时 dedup

### 现状审计

当前代码已使用 **replace** (而非 append) 策略写入 frontmatter 字段：

| 工具 | 字段 | 写入方式 |
|------|------|----------|
| `set_status.py` | `> 状态:` | regex match → replace 整行 |
| `confirm_risk.py` | `> 风险:` | regex match → replace 整行 |
| `confirm_risk.py` | `> 风险确认:` | regex match → replace 整行 |
| `spec_amend.py` | `> Prompt version:` | regex match → replace 整行 |
| `spec_amend.py` | `> 风险确认:` | regex match → replace 整行 |

**结论**: 正常调用流程下，工具不会产生重复 frontmatter 字段。

### 历史重复根因

妙藏 4 specs 的重复来自 **旧版本工具 bug** 或 **手动编辑**，已被 commit 7851a68 修复。

### 状态

- 新数据: ✅ 不会重复 (replace 策略)
- 历史数据: ✅ 已手动修复 (7851a68)
- 未来防护: ⏳ 低优先级，如再发生可 retrofit

---

## Skill 版本信息

- **当前 HEAD**: `e74b2e8` (auto-refresh plan digest)
- **安装路径**: `~/.pi/agent/skills/vibe-coding`
