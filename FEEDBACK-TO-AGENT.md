# 给 Agent 的反馈 — Skill 升级已完成（2026-07-13）

管理员已评审候选：`skill-upgrade-candidate-20260713.md`（Rule 53 step 1 active inspection 机械检查缺口）

**候选已归档**: `.agents/archive/skill-upgrade-candidates/skill-upgrade-candidate-20260713.md`

---

## 候选处理结果

**状态**: 已采纳 ✅（轻量方案）

**Commit**: `e8a6b9e` — feat(skill): R53 active inspection advisory on review gate block
**VERSION**: `e8a6b9e-r53-active-inspection-advisory`

---

## 为什么选轻量方案，不选强方案

| 方案 | 做法 | 不选原因 |
|------|------|---------|
| **强方案** | 门禁拦截后，下次提交要求 review-summary 必须包含"已重读 <file>: <具体观察>" | Agent 可以编造观察，机械检查无法验证。新增硬 gate 增加规则臃肿，绕过激励更强 |
| **轻量方案** ✅ | 门禁拦截后输出 advisory，提醒 Agent"你真的重读了 diff，不是只补格式" | 不阻塞流程，但形成心理提醒。retro 模板新增自检项，促进 retro 阶段反思 |

**核心原则**: 形式合规 ≠ 实质审查。硬 gate 只能管格式，管不了 Agent 是否真读。advisory + retro 自检是更务实的方式。

---

## 改了什么

### 1. commit.py — 门禁拦截后输出 advisory

当 review-summary 被 `missing_file_review` 或 `missing_line_refs` 门禁拦截时，现在会输出：

```
💡 拦截提醒 — 你被拦了，但门禁只检查格式
   请确认你真的重读了 diff 内容，不是只补文件名引用。
   review-summary 必须包含对 diff 的实际观察（如行号、代码片段），
   不能只是列出文件名。
```

```
💡 拦截提醒 — 你被拦了，但门禁只检查行号引用格式
   请确认你真的重读了 diff 内容，不是只补行号/反引号。
   review-summary 必须包含基于 diff 观察的业务结论，
   不能只是形式合规（如 'L25 重命名，语义等价' 但没有真的看每个调用点）
```

### 2. retro.md — Review Agent 段新增 review quality 自检

```
- **review quality 自检**（2026-07-13 R53 active inspection）:
  - review-summary 是否包含对每个变更文件的实际观察（非记忆性描述）
  - 是否检查了每个文件 diff 的具体行号和代码片段
  - 是否有"形式合规但内容未审查"的情况（如只补行号未重读）
  - review-decision basis 是否引用了 review-context 文件路径
  - 如果 review gate 拦截了，是否重读了被拦的文件，还是只补格式
```

### 3. 测试覆盖

- `test_active_inspection_advisory_on_missing_file_block` — missing_file_review 拦截时 advisory 输出
- `test_active_inspection_advisory_on_line_ref_block` — missing_line_refs 拦截时 advisory 输出

---

## 对 Agent 的影响

**当 review gate 拦截你时**：

1. 你会看到 advisory 提醒"请确认你真的重读了 diff"
2. 不要只是补格式（加文件名、行号、反引号）就重试
3. 真正重新读一遍 diff，然后写基于观察的 review-summary
4. retro 阶段检查 review quality 自检项

**写 retro 时**：
- Review Agent 段新增了 5 条自检项
- 如实填写"是否有形式合规但内容未审查的情况"
- 如果 review gate 拦截了，说明 retro 里要写清楚"被拦了几次，是否重读了"

---

## 今日全部 5 项升级汇总

| # | 升级 | Commit | 说明 |
|---|------|--------|------|
| 1 | vibe next 自动 doctor | `a8bc97b` | 每次 `vibe next` 前自动跑 doctor |
| 2 | commit-msg hook 修复 | `a8bc97b` | 修正 hook 类型 + 测试绕过 |
| 3 | evidence digest 过期检测 | `d12d433` | amend 后自动检测并提示 |
| 4 | Skill 升级提案标准化 | `365025e` | 新增 `vibe propose-skill-upgrade` 命令 + 自动检测未归档提案 |
| 5 | **R53 active inspection advisory** | `e8a6b9e` | 门禁拦截后提醒 Agent 重读 diff，不补格式 |

---

## 当前完整标准操作

```bash
# 初始化项目
vibe init <path>

# 查看下一步（自动跑 doctor + 检测未归档提案）
vibe next <project>

# 创建 skill 升级候选提案
vibe propose-skill-upgrade <project> "<标题>"

# 修改 spec（自动检测 evidence digest 过期）
vibe amend <project> <spec> "变更描述" --apply

# 提交代码（两步）
vibe commit <project>              # 看 diff，被拦时读 advisory
vibe commit --reviewed <project>   # verify + commit

# 写 retro（Review Agent 段新增 review quality 自检）
vibe retro <project> <spec>
```

---

## 测试状态

- 597 个测试全部通过
- VERSION: `e8a6b9e-r53-active-inspection-advisory`
