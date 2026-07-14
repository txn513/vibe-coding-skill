# 反馈给项目 Agent — Skill 升级候选评估结果 (20260713m)

## 评估结论

| 候选 | 内容 | 结论 | 理由 |
|------|------|------|------|
| 候选1 | schema-orm-mismatch 自动化检测 | ⏸ **暂缓** | 依赖特定技术栈 (SQLAlchemy + Alembic)，非通用 Skill 级 |

---

## ⏸ 候选1 — 暂缓 (schema-orm-mismatch)

**标题**: schema-orm-mismatch 自动化检测

### 暂缓理由

1. **技术栈绑定**: 提案依赖 SQLAlchemy + Alembic，不是通用 Skill 级规则
2. **项目级更合适**: 建议在项目 `.agents/rules/` 中定义项目级规则 + 项目级 pre-commit hook
3. **已有覆盖**: `vibe doctor` 支持 project-specific checker 插件，可在项目级接入

### 建议项目级落地

```markdown
# .agents/rules/schema-migration.md

## Rule: ORM 改动必须同步 Alembic migration

### Binding
- pre-commit hook: .agents/hooks/check-alembic.sh
- CI workflow: .github/workflows/migration-check.yml

### 检查清单
- [ ] ORM 模型新增/修改/删除 field → 必须同步 Alembic migration
- [ ] migration 文件已生成 (`alembic revision --autogenerate`)
- [ ] migration 已本地测试 (`alembic upgrade head`)
```

### 状态

- Skill 级: ⏸ 暂缓 (技术栈太具体)
- 项目级: 💡 建议妙藏自行落地

---

## Skill 版本信息

- **当前 HEAD**: `e8ca8fa` (spec degradation path)
