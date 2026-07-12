# Skill 升级候选 — evidence digest 过期自动检测

来源: retro-20260712-fix-stream-dns-rebinding.md（沉淀落点段）
日期: 2026-07-13
标题: spec amend 后自动检测 evidence digest 过期
状态: **已采纳**

---

## 候选：evidence digest 过期自动检测（governance 级）

**问题**：spec review feedback 后 amend，已记录 evidence 的 spec digest 过期，导致 `vibe advance` 报"缺少 evidence"。

**建议方案**：
- `vibe amend` / `spec_amend.py` 修改 spec 后自动扫描关联 evidence
- 比较 evidence header 的 `spec_digest` 与当前 spec digest
- 不匹配时输出 advisory 提醒重新记录
- advisory only，不自动刷新（防掩盖失效 evidence）

**通用性审计**：
- ✅ 通用：所有项目都有 spec + evidence
- ✅ 不含项目知识：纯 metadata 比较
- ✅ 跨项目适用：是
- 失败模式：rule exists, but compliance is not enforced

**影响范围**：所有使用 `vibe amend` 的项目

**实施复杂度**：低

**预期收益**：避免 spec amend 后 evidence digest 过期导致的 advance 门禁误报

---

## 管理员反馈

### 状态：已采纳 ✅

- **实施 commit**: `d12d433` — feat(skill): evidence digest stale auto-detection on spec amend
- **实施日期**: 2026-07-13
- **测试覆盖**: 592 tests pass（新增 3 个 case）
