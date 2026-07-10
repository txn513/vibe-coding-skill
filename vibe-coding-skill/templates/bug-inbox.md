# Bug Inbox

> 最后同步到 catalog: YYYY-MM-DD
>
> Bug 入口 ledger (append-only). 任何项目级 bug 跟踪都从此文件开始.
> 流程: bug 报告 → 二次验证 → 修复 → spec done → 关闭 ([ ] → [x])

## 风险级别与二次验证矩阵 (对齐 Skill R10)

| 风险级别 | 二次验证方式 | Skill 对应 |
|---------|------------|-----------|
| **P1/P2 (高风险)** | 走 vibe spec 完整 reproduction 流程 | R10 (reproduction + fix-regression 双向证据) |
| **P3 (中风险)** | 静态读代码 + 复现脚本 (静态不够时) | R10 子集 (reproduction 可省) |
| **P4 (低风险)** | 静态读代码足够 | 不需要 R10 |

## 验证笔记格式 (强制)

每条 inbox bug 行必须有至少一条验证笔记, 缩进子项格式:

```
- [ ] P3: bug 描述 — file.py:123 (YYYY-MM-DD)
  - 验证 (YYYY-MM-DD, 验证人): ✅/❌/⚠️ + 具体结论 (完整路径 + 行号 + 代码片段)
```

- ✅ 真实存在 → 保留 `[ ]` 等修
- ❌ 不成立 (bug 已修 / 描述失效 / 行号飘了找不到代码) → 必须 `[ ]` 改 `[x]` + 笔记说明失效原因
- ⚠️ 部分成立 → 补二次验证或笔记详细说明哪部分成立

emoji ✅ ❌ ⚠️ 不能替代 `[x]` (破坏 markdown checkbox 语义, 漂移检测会失效).

## 关闭规则

- 验证为 ❌ / 已修 → `[ ]` 改 `[x]` + 加笔记 `关闭 (YYYY-MM-DD, <actor>): ✅/❌ <原因>`
- 验证为 ✅ → 保留 `[ ]` 等修
- 不删行 (append-only ledger), 关闭只改 checkbox + 加笔记

## 同步规则 (强制) — 修任何 inbox bug 必须同步

1. **修 inbox bug 之前**: 读 inbox 找对应 bug 行, 确认行号/描述
2. **修完落地 (commit + spec done) 同一 commit chain 内**:
   - bug 行 `[ ]` → `[x]`
   - 加关闭笔记: `关闭 (YYYY-MM-DD, <actor>): ✅ 已修 — <commit-sha> (<spec-name> done)`
3. **涉及 hotfix** (用户直接报告) 不在 inbox ledger: 不需要更新, 但应在 commit message 引用 inbox bug 描述
4. **新发现 bug** (非 hotfix): append 到 `## YYYY-MM-DD 扫描批次` 段, 走二次验证规范
5. **误判关闭**: `[ ]` → `[x]` + 加笔记 `关闭 (YYYY-MM-DD, <actor>): ❌ <原因>`

任何 spec done 但 inbox 还有相关 `[ ]` bug = 流程违规. Skill `vibe doctor` 在 opt-in 启用 inbox drift 检测时会强制 warn.

## 速查命令 (可选)

- 查今天修了哪些 (按关闭日期):
  `grep -E "(修复|关闭) \(YYYY-MM-DD" .agents/bug-inbox.md`
- 查某 commit 是否关联 bug:
  `grep "<commit-sha>" .agents/bug-inbox.md`
- 查某 spec 修了哪些 bug:
  `grep -B1 "spec <name> done" .agents/bug-inbox.md`
- 查所有 open bug (排除误判):
  `grep -cE "^\- \[ \] " .agents/bug-inbox.md`
- 查所有 closed bug 数量:
  `grep -cE "^\- \[x\] " .agents/bug-inbox.md`

## 历史记录

(从这里开始 append 新 bug 行, 按日期分批)
