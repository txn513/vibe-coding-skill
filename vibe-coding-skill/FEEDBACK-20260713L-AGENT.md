# 反馈给项目 Agent — Skill 升级候选评估结果 (20260713l)

## 评估结论

| 候选 | 内容 | 结论 | 理由 |
|------|------|------|------|
| 候选1 | verify 段加 degradation path 子段 | ✅ 已采纳 (模板级) | 1.8% retro 命中率，通用 happy-path bias，模板级修复成本低 |

---

## ✅ 候选1 — 已采纳 (commit e8ca8fa)

**标题**: verify 段加 `### 降级路径 (Degradation Path)` 子段

### 已实现

`templates/spec.md` 已改：

```markdown
## 验证方式

### 正常路径 (Happy Path)
- [ ] 相关回归测试已新增或更新
- ...

### 降级路径 (Degradation Path)
> 如果 spec 涉及降级、失败 fallback、异常处理等场景，必须在此验证。
> 如果无降级场景，写 "N/A" 并说明原因。

- [ ] 失败场景: <描述失败条件>
- [ ] 降级行为: <描述 fallback 行为>
- [ ] 用户感知: <toast / 404 / 默认值 / 重试 / ...>
- [ ] 验证证据: <evidence 文件路径或 test 引用>
```

### 效果

- 新 spec 默认带 degradation path 检查清单
- Agent 写 verify 时必须考虑降级场景
- retro 时检查 degradation path 覆盖率有依据

### 与提案的差异

| 提案层 | 状态 | 说明 |
|--------|------|------|
| templates/spec.md 加子段 | ✅ 已采纳 | 见 commit e8ca8fa |
| record_evidence.py coverage check | ⏸ 暂缓 | 模板级先落地，工具级后补 |
| set_status.py advance 校验 | ⏸ 暂缓 | 同上，retro 沉淀后评估 |

---

## Skill 版本信息

- **当前 HEAD**: `e8ca8fa` (spec degradation path)
- **安装路径**: `~/.pi/agent/skills/vibe-coding`
