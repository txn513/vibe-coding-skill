# {{SPEC_NAME}} — 回顾

> 上线日期: {{SHIP_DATE}} | 回顾日期: {{RETRO_DATE}} | 参与者: {{PARTICIPANTS}}

## 失败模式分类

- **主失败模式**: {{PRIMARY_FAILURE_MODE}}
- **次级失败模式**: {{SECONDARY_FAILURE_MODE}}
- **为什么归到这个类别**: {{FAILURE_MODE_RATIONALE}}

## 目标回顾

**最初意图**: {{ORIGINAL_INTENT}}

**实际交付**: {{ACTUAL_DELIVERY}}

**差异分析**: {{GAP_ANALYSIS}}

## 做对了什么

- {{WENT_WELL_1}}
- {{WENT_WELL_2}}
- {{WENT_WELL_3}}

## 做错了什么

- {{WENT_WRONG_1}}
- {{WENT_WRONG_2}}
- {{WENT_WRONG_3}}

## 行为变化记录 (Rule 58)

> 如果本 spec 改变了已有行为（涉及范围中标注为"修改"或"删除"的读取路径），以下 4 项必须填写。
> 如果没有改变已有行为，写"无行为变化"即可。

- **行为变化描述** (改之前 vs 改之后): {{BEHAVIOR_CHANGE_DESC}}
- **影响范围** (谁/什么受影响): {{IMPACT_SCOPE}}
- **业务决策** (为什么接受这个变化): {{BUSINESS_DECISION}}
- **回退方案** (如何恢复原来行为): {{ROLLBACK_PLAN}}

## 结论证据

> **⚠️ 必填**: 若"做错了什么"包含真实结论 (bug / 失败 / 回归 / 行为异常), 本段必须引用至少一种 evidence; 否则 `--strict` 复盘会 fail-fast。
>
> 可用 evidence 类型: 复现命令 / logcat / dumpsys / 单元测试 / 截图 / 堆栈 / diff / `unverified historical note` 标注。

如果上面的失败、Bug、回归或行为异常结论已经复验，请引用证据；如果只是历史观察，请明确标注未复验。

**项目内路径引用格式 (项目内使用统一的单引号半角格式)**:

```text
合同: '.agents/specs/example/ui-design-contract.md'
证据: '.agents/evidence/example/verify.md'
复现: '.agents/evidence/example/verify-reproduction.md'
```

- **证据引用**: {{CLAIM_EVIDENCE}}
- **未复验结论**: {{UNVERIFIED_CLAIMS}}

## 流程遵守审计

> 本次 spec 是否严格遵守了 Vibe Coding 工作流？如实填写，这会影响 self_analyze 的治理候选生成。

- [ ] **Discovery**: 是否记录了 intent？（是 / 否 / 不适用）
  - 如果不适用，原因：
- [ ] **Spec**: 是否经过 spec-ready 检查？（是 / 否）
- [ ] **Plan**: 是否有实施计划？（是 / 否）
- [ ] **Execute**: 是否使用 `vibe commit` 提交？（是 / 否）
  - 如果使用了 `git commit` 直接提交，原因：
  - 是否事后用 `git reset --soft` 修复？（是 / 否 / 不适用）
- [ ] **Verify**: evidence 是否在 advance 前完成？（是 / 否）
- [ ] **Review**: 是否有独立 reviewer？（是 / 否）
  - reviewer 与 builder 是否为同一身份？（是 / 否）
- [ ] **Retro**: 是否在 done 后立即写 retro？（是 / 否）

**如果任何一项为"否"，请说明原因和当时的判断：**
{{WORKFLOW_SKIP_REASON}}

**心态自检**：我是否因为"觉得 vibe 规范是可选的 overhead"而跳过它？
如果是，请回忆上一次跳过 review 后引入的 bug —— 那正是 vibe commit 要防止的。

## Agent 表现评估

### 实现 Agent
- **擅长**: {{BUILDER_STRENGTHS}}
- **反复出错**: {{BUILDER_WEAKNESSES}}
- **需要补充的规则**: {{BUILDER_MISSING_RULES}}

### Review Agent
- **发现的真实问题**: {{REVIEWER_FOUND}}
- **漏掉的问题**: {{REVIEWER_MISSED}}
- **review quality 自检**（2026-07-13 R53 active inspection）:
  - review-summary 是否包含对每个变更文件的实际观察（非记忆性描述）
  - 是否检查了每个文件 diff 的具体行号和代码片段
  - 是否有"形式合规但内容未审查"的情况（如只补行号未重读）
  - review-decision basis 是否引用了 review-context 文件路径
  - 如果 review gate 拦截了，是否重读了被拦的文件，还是只补格式

## 规格质量

- **哪些约束写对了**: {{SPEC_CONSTRAINTS_GOOD}}
- **哪些约束漏了**: {{SPEC_CONSTRAINTS_MISSING}}
- **验收标准是否覆盖了所有线上情况**: {{AC_COVERAGE}}

## 上下文质量

- **AGENTS.md 是否准确**: {{AGENTS_ACCURACY}}
- **规则文件是否有误导**: {{RULES_ISSUES}}
- **Agent 是否理解了项目结构**: {{CONTEXT_UNDERSTANDING}}

## 沉淀落点

- **项目内应更新什么**: {{PROJECT_UPDATES}}
- **是否形成 Skill 治理候选**: {{SKILL_CANDIDATE}}
- **如果形成，候选摘要是什么**: {{SKILL_CANDIDATE_SUMMARY}}

> 💡 Skill 升级候选提案规范（2026-07-13 起）:
>   - 如果 retro 发现可跨项目复用的治理改进，**必须**写入 `.agents/skill-upgrade-candidates/`
>   - 命名规范: `skill-upgrade-candidate-YYYYMMDD.md`，同一天多份加后缀 `b`, `c` 等
>   - 创建命令: `vibe propose-skill-upgrade <project> "<标题>"`
>   - 模板内容: 候选标题 / 分类(governance/project) / 问题描述 / 建议方案 / 通用性审计 / 预期收益
>   - 管理员评审后归档到 `.agents/archive/skill-upgrade-candidates/`
>   - `vibe next` 会自动检测未归档的提案并提醒管理员评审

## 沉淀清单 (R-沉淀-enforcement)

> 每条沉淀必带 R6.1 三选一 tag + id + 层级. 无 tag 或层级不明 = 形式合规假阳性。

### 沉淀格式

```
- [<tag>: <id>] (<层级>) <description>
```

**tag 四选一**:
- `[active: <spec-id>]` → 已建 / 待建 follow-up spec
- `[deferred: <触发条件>]` → 推迟, 触发条件必明示
- `[superseded: <replaced-by>]` → 被哪个 spec / commit 替代
- `[永不: <justification>]` → 明确放弃 + 理由

**层级二选一** (强制):
- `(项目级)` → 只影响本项目 (项目规则 / 项目代码 / 项目配置)
- `(skill 级)` → 跨项目通用 (Skill 规则 / 工具 / 模板)

### 示例

- [active: fix-parser-bug] (项目级) parser 在空输入时崩溃 → 已建 spec, 待 advance
- [deferred: next spec cycle] (项目级) 性能优化 → 等当前 batch 完成后启动
- [superseded: 62603de] (skill 级) doctor parser 扩展 keywords → 已合并到 Skill
- [永不: 业务上不需要] (项目级) 支持 IE11 → 明确放弃

> 无 tag 或层级不明 = retro 不完整. `vibe next` 会扫描本段并提醒.

## 行动项

- [ ] 更新 AGENTS.md: {{ACTION_AGENTS}}
- [ ] 更新规则文件: {{ACTION_RULES}}
- [ ] 更新 spec 模板: {{ACTION_SPEC_TEMPLATE}}
- [ ] 更新 review checklist: {{ACTION_REVIEW_CL}}
- [ ] 其他: {{ACTION_OTHER}}

## 开放 gap（可选）

> 提示：如果你想 Skill 在新 verify evidence 写入时提示"此 gap 可能已闭合"，
> 可以在这里列出。每条至少包含一个 spec 名（kebab-case），例如：
>
> - 端到端还没跑通 (auth-refactor)
> - cache 失效路径未验证 (api-cache)
>
> Skill 不会自动写 retro，闭合判断永远由你确认。
