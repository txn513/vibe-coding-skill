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

## Agent 表现评估

### 实现 Agent
- **擅长**: {{BUILDER_STRENGTHS}}
- **反复出错**: {{BUILDER_WEAKNESSES}}
- **需要补充的规则**: {{BUILDER_MISSING_RULES}}

### Review Agent
- **发现的真实问题**: {{REVIEWER_FOUND}}
- **漏掉的问题**: {{REVIEWER_MISSED}}

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
