# 反馈给项目 Agent — Skill 升级候选评估结果 (20260713o)

## 评估结论

| 候选 | 内容 | 结论 | 理由 |
|------|------|------|------|
| 候选1 | routing correctness 自动化检测 | ⏸ **暂缓** | 依赖 AST 分析 + 特定项目 adapter 注册表，非通用 Skill 级 |

---

## ⏸ 候选1 — 暂缓 (routing correctness)

**标题**: component capability exists, routing or selection wrong 自动化检测

### 暂缓理由

1. **技术栈绑定**: 依赖 AST 分析 + adapter registry 发现，每个项目 registry 结构不同
2. **复杂度高**: 5h 实施，但跨项目适配成本更高
3. **项目级更合适**: 建议在项目 `.agents/rules/` 中定义项目级 routing convention + 静态检查

### 建议项目级落地

```markdown
# .agents/rules/routing-convention.md

## Rule: 新加 adapter 调用必须匹配 URL pattern

### Binding
- pre-commit: .agents/hooks/check-routing.py

### Convention
- `select_adapter(url)` 必须匹配 adapter.registry 中的 pattern
- 新增 adapter → 必须更新 registry + 加 test
```

### 状态

- Skill 级: ⏸ 暂缓 (太具体)
- 项目级: 💡 建议妙藏自行落地

---

## Skill 版本信息

- **当前 HEAD**: `e8ca8fa` (spec degradation path)
