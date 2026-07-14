# 支持的 Hook 类型

| Hook | 触发时机 | 适用规则 |
|------|---------|---------|
| `tool_call` | Agent 调用工具时 | R53 (block git commit), R4/R5/R10 (advisory) |
| `before_agent_start` | Agent 启动前 | R66 (inject system prompt) |
| `agent_end` | Agent 结束时 | R1 (check gates) |
| `input` | 用户输入时 | 未来：检查输入是否符合 vibe 命令格式 |
| `turn_start` | 每个 turn 开始时 | 未来：检查 session 是否 stale |
| `turn_end` | 每个 turn 结束时 | 未来：记录 turn 摘要到 activity |
| `after_provider_response` | LLM 响应后 | 未来：检查 LLM 是否提到需要 retro |

## 扩展方式

在 `registerHandlers` 的 `switch (rule.hook)` 里加新的 case：

```typescript
case "input": {
  pi.on("input", async (event, ctx) => {
    // event.prompt 是用户输入的文本
    if (rule.action === "check_format") {
      // 检查输入是否符合 vibe 命令格式
    }
  });
  break;
}
```
