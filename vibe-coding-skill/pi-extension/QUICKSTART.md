# Vibe Enforcer 快速上手

## 安装（3 步）

```bash
# 1. 确认 skill 路径
ls ~/.pi/agent/skills/vibe-coding/SKILL.md || \
  ln -s /path/to/vibe-coding-skill ~/.pi/agent/skills/vibe-coding

# 2. 安装 Extension
ln -s /path/to/vibe-coding-skill/pi-extension/vibe-enforcer.ts \
  ~/.pi/agent/extensions/vibe-enforcer.ts

# 3. 验证
pi
# 启动后看日志：[vibe-enforcer] Loaded 8 enforce rules
```

---

## 验证拦截（R53 示例）

```bash
# 在 Pi 交互模式下，让 Agent 执行：
> git commit -m "test"

# 预期输出：
⚠️ R53: 请使用 vibe commit，禁止 raw git commit

# Agent 被 block，必须使用：
> vibe commit --reviewed
```

---

## 验证注入（R66 示例）

```bash
# 在 Pi 交互模式下，compact 后新对话：
> /compact

# 预期输出（自动注入 system prompt）：
## AGENT-MANDATORY (R66)
会话恢复后必须先运行 vibe status + vibe next

# Agent 会看到这个提示，然后执行：
> vibe status
> vibe next
```

---

## 修改规则（改一次，两边生效）

```bash
# 编辑 SKILL.md
vim /path/to/vibe-coding-skill/SKILL.md

# 添加新的 ENFORCE 注释
<!-- ENFORCE: id=R99, hook=tool_call, tool=bash, match=vibe foo, action=block, message=禁止 -->

# 保存，退出 Pi，重新启动
exit
pi
# 日志：[vibe-enforcer] Loaded 9 enforce rules
```

---

## 卸载

```bash
rm ~/.pi/agent/extensions/vibe-enforcer.ts
```
