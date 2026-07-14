# 反馈给项目 Agent — Skill 升级候选评估结果 (20260713n)

## 评估结论

| 候选 | 内容 | 结论 | 理由 |
|------|------|------|------|
| 候选1 | rule-binding 自动校验 | ⏸ **部分采纳 (模板级)** | 1.3% retro 命中率，Binding 段已在 spec/retro 模板有，rule 模板可补 |

---

## ⏸ 候选1 — 部分采纳 (rule-binding 校验)

**标题**: rule → gate 绑定自动校验

### 现状

当前模板已含 binding 机制（间接）：

| 模板 | 已有 binding |
|------|-------------|
| `spec.md` | ✅ verify 段 → `vibe verify` gate |
| `retro.md` | ✅ 沉淀落点 → `vibe next` scan |
| `plan.md` | ✅ digest header → `vibe plan --refresh-digest-only` |

### 与提案的差异

| 提案层 | 状态 | 说明 |
|--------|------|------|
| `.agents/rules/*.md` 加 Binding 段 | 💡 建议项目级 | Skill 级不加硬约束，留项目灵活性 |
| `rules_binding_check.py` | ⏸ 暂缓 | 1.3% 命中率，ROI 不高 |
| doctor 集成 | ⏸ 暂缓 | 同上 |

### 建议

- 项目级 rule 作者手动在 rule 文档顶部写 `Binding:` 段
-  retro 沉淀时检查 rule 是否有对应 gate
-  高优先级 rule (如 R-D-6) 可单独绑定到 doctor

---

## Skill 版本信息

- **当前 HEAD**: `e8ca8fa` (spec degradation path)
