# Vibe Enforcer — Pi Extension

> 让 vibe-coding skill 的规则从"建议"变成"强制"。

## 原理

Pi Extension 启动时自动读取 `SKILL.md` 里的 `<!-- ENFORCE -->` 注释，根据注释中的 `hook` 和 `action` 注册对应的事件拦截器。

**你改 SKILL.md，Extension 自动同步。**

```
你改的内容 → SKILL.md → Pi 启动时 Extension 解析 → 自动注册拦截器
```

---

## 安装

### 1. 确认 vibe-coding skill 已安装

```bash
# skill 必须在 Pi 能找到的地方
ls ~/.pi/agent/skills/vibe-coding/SKILL.md
# 如果不在，创建软链接：
# ln -s /path/to/vibe-coding-skill ~/.pi/agent/skills/vibe-coding
```

### 2. 创建 Extension 目录

```bash
mkdir -p ~/.pi/agent/extensions/
```

### 3. 安装 Extension

```bash
ln -s $(pwd)/pi-extension/vibe-enforcer.ts ~/.pi/agent/extensions/vibe-enforcer.ts
```

或者如果你用项目级 extensions：

```bash
mkdir -p .pi/extensions
ln -s $(pwd)/pi-extension/vibe-enforcer.ts .pi/extensions/vibe-enforcer.ts
```

### 4. 验证安装

```bash
# 启动 Pi，看 Extension 是否加载
pi
# 应该能看到输出：
# [vibe-enforcer] Skill found: .../SKILL.md
# [vibe-enforcer] Loaded 8 enforce rules
```

---

## 验证拦截（R53 示例）

在 Pi 交互模式下，让 Agent 执行：

```
> git commit -m "test"
```

预期输出：

```
⚠️ R53: 请使用 vibe commit，禁止 raw git commit
```

Agent 被 block，必须使用：

```
> vibe commit --reviewed
```

---

## 修改规则（改一次，两边生效）

### 1. 编辑 SKILL.md

```bash
vim /path/to/vibe-coding-skill/SKILL.md
```

找到想加强的规则，在规则标题前加 `<!-- ENFORCE -->` 注释：

```markdown
<!-- ENFORCE: id=R99, hook=tool_call, tool=bash, match=vibe foo, action=block, message=禁止 -->
## Rule 99: Foo Bar
```

### 2. 字段说明

| 字段 | 必填 | 值 | 说明 |
|------|------|-----|------|
| `id` | ✅ | 如 `R99` | 规则编号 |
| `hook` | ✅ | `tool_call` / `before_agent_start` / `agent_end` | 拦截时机 |
| `action` | ✅ | `block` / `inject_prompt` / `notify` | 拦截行为 |
| `tool` | 条件 | `bash` / `edit` / `read` / `write` | 指定工具名 |
| `match` | 条件 | 正则字符串 | 匹配工具参数 |
| `message` | 否 | 提示语 | block/notify 时显示 |

### 3. 重启 Pi

Extension 在 Pi 启动时解析 SKILL.md，所以**每次改完 SKILL.md 后必须重启 Pi**。

```bash
# 退出 Pi
exit

# 重新启动
pi
```

---

## 当前生效的 8 条规则

| 规则 | Hook | 行为 |
|------|------|------|
| R1 | `agent_end` | 检查 gate 是否全部通过 |
| R4 | `tool_call` (bash) | 拦截 `vibe verify/evidence`，确保运行了配置的命令 |
| R5 | `tool_call` (bash) | 拦截 `vibe next.*review`，检查 reviewer 身份 |
| R10 | `tool_call` (bash) | 拦截 bug fix 的 verify，要求双向证据 |
| R22 | `tool_call` (bash) | 拦截 `vibe next`，检查 stage transition gate |
| R25 | `tool_call` (bash) | 拦截 `vibe retro`，检查 failure mode label |
| R53 | `tool_call` (bash) | **block** `git commit`（非 vibe commit） |
| R66 | `before_agent_start` | 注入 session recovery 提示 |

---

## 常见问题

### Extension 没加载？

检查路径：

```bash
ls ~/.pi/agent/extensions/vibe-enforcer.ts
# 如果不在，检查软链接是否正确
```

### 规则没生效？

1. 确认 Pi 重启了（Extension 只在启动时解析 SKILL.md）
2. 检查 Pi 启动日志是否有 `[vibe-enforcer] Loaded X enforce rules`
3. 检查 `SKILL.md` 里的 `<!-- ENFORCE -->` 注释格式是否正确

### 只想用 Skill，不想用 Extension？

直接删除 Extension 软链接即可，Skill 不受影响：

```bash
rm ~/.pi/agent/extensions/vibe-enforcer.ts
```

---

## 技术细节

### Extension 查找 SKILL.md 的顺序

```typescript
1. ~/.pi/agent/skills/vibe-coding/SKILL.md      (Pi 全局)
2. ~/.agents/skills/vibe-coding/SKILL.md         (跨 Agent 兼容)
3. ./.pi/skills/vibe-coding/SKILL.md            (Pi 项目级)
4. ./.agents/skills/vibe-coding/SKILL.md         (项目级兼容)
5. <extension_dir>/../../vibe-coding/SKILL.md     (同级目录)
6. <extension_dir>/../vibe-coding/SKILL.md       (父目录)
```

### 向后兼容

- **Codex / Claude / Cursor**：直接忽略 `<!-- ENFORCE -->` HTML 注释
- **Pi**：Extension 解析注释并注册拦截器
- 纯 Skill Agent 不受影响

---

## 卸载

```bash
rm ~/.pi/agent/extensions/vibe-enforcer.ts
```

Skill 仍然可用。
