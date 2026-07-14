# ENFORCE 注释 Schema — vibe-coding skill

> 作用: 让 Pi Extension 运行时自动解析 SKILL.md 里的规则，生成对应的拦截/注入逻辑。
> 原则: 一个规则只改一处（SKILL.md），Extension 启动时自动同步。

## 格式

```
<!-- ENFORCE: id=<RULE_ID>, hook=<HOOK>, action=<ACTION>[, param1=val1, param2=val2] -->
## <规则标题>

<规则正文...>
```

## 字段

| 字段 | 必填 | 值 | 说明 |
|------|------|-----|------|
| `id` | ✅ | 如 `R53` | 规则编号，全局唯一 |
| `hook` | ✅ | `tool_call` / `before_agent_start` / `input` / `agent_end` | Pi 生命周期事件 |
| `action` | ✅ | `block` / `inject_prompt` / `notify` / `require_evidence` | 触发后的行为 |
| `condition` | 条件必填 | 取决于 hook | 匹配条件（见下） |
| `message` | 否 | 提示语 | block/notify 时显示的文字 |

## Hook 详情

### hook=tool_call

拦截工具调用，常用于阻止危险操作。

| 子字段 | 必填 | 值 | 说明 |
|--------|------|-----|------|
| `tool` | ✅ | `bash` / `edit` / `read` / `write` | 工具名 |
| `match` | ✅ | 正则字符串 | 匹配工具参数（如 `git commit`） |
| `action` | ✅ | `block` / `notify` / `replace` | 行为 |

**示例：**
```markdown
<!-- ENFORCE: id=R53, hook=tool_call, tool=bash, match=git commit(?!.*vibe), action=block -->
## Rule 53: vibe commit 两步制

任何 commit 必须通过 `vibe commit` 完成，禁止 raw `git commit`。
```

### hook=before_agent_start

在 agent 启动前注入 system prompt 片段。

| 子字段 | 必填 | 值 | 说明 |
|--------|------|-----|------|
| `action` | ✅ | `inject_prompt` | 行为 |

**示例：**
```markdown
<!-- ENFORCE: id=R66, hook=before_agent_start, action=inject_prompt -->
## Rule 66: Session Recovery

任何会话恢复/compact 后，必须先运行 `vibe status`。
```

### hook=agent_end

Agent 一轮结束后检查。

| 子字段 | 必填 | 值 | 说明 |
|--------|------|-----|------|
| `action` | ✅ | `require_evidence` / `require_retro` | 行为 |
| `spec_status` | 条件 | `done` / `released` | 触发条件 |

**示例：**
```markdown
<!-- ENFORCE: id=R-retro, hook=agent_end, action=require_retro, spec_status=done -->
## Retro 沉淀

spec 到达 done 后必须写 retro。
```

## 解析规则

1. `<!-- ENFORCE -->` 必须紧跟在规则标题 `## ` 之前（同一行或前一行）
2. 多个 `ENFORCE` 可作用于同一条规则（如同时 block + notify）
3. Extension 启动时扫描整个 SKILL.md，提取所有 ENFORCE 注释
4. 解析失败时输出警告，但不阻塞 Extension 启动

## 向后兼容

- 纯 Skill Agent（Codex / Claude / Cursor）直接忽略 HTML 注释，不受影响
- 只有 Pi Extension 会解析并执行这些注释
