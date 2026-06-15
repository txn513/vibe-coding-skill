# Policy Confirmations

> Generated: 2026-06-14 09:37 UTC

## How To Use

- Confirm whether the source is still authoritative.
- Choose one landing: `workflow.json`, project rules / AGENTS, or explicit conflict.
- Replace `pending` markers with the project decision.

## Pending Items

### CONTRIBUTING.md

- Source ID: `contributing`
- Path: `CONTRIBUTING.md`
- Suggested landing: `.agents/rules/*.md 或 AGENTS.md`
- Suggested action: 确认 CONTRIBUTING.md 并沉淀为项目规则
- Why: 这类来源通常是协作约束、开发约定或本地事实，应该先落到项目规则层。

Candidate Patch

- Type: rule draft (`.agents/rules/contributing.md`)
```text
# CONTRIBUTING.md

> 状态: proposed

## Rule

- Source: CONTRIBUTING.md
- Pending project-specific instruction goes here.

## Adoption

- Why this should become a project rule: pending
```

Decision

- Authority status: pending
- Chosen landing: pending
- Planned update: pending
- Conflict needed: pending

Notes

- 确认其中的提交、评审、分支或发布要求是否应视为强制规范。
- Fallback: 若与现有项目规则冲突，记录 explicit conflict

### README.md

- Source ID: `readme`
- Path: `README.md`
- Suggested landing: `.agents/rules/*.md 或 AGENTS.md`
- Suggested action: 确认 README.md 并沉淀为项目规则
- Why: 这类来源通常是协作约束、开发约定或本地事实，应该先落到项目规则层。

Candidate Patch

- Type: rule draft (`.agents/rules/readme.md`)
```text
# README.md

> 状态: proposed

## Rule

- Source: README.md
- Pending project-specific instruction goes here.

## Adoption

- Why this should become a project rule: pending
```

Decision

- Authority status: pending
- Chosen landing: pending
- Planned update: pending
- Conflict needed: pending

Notes

- 确认 README 中的开发和运行方式是否仍代表当前项目事实。
- Fallback: 若与现有项目规则冲突，记录 explicit conflict
