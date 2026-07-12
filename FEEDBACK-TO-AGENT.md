# 给 Agent 的反馈 — Skill 升级已完成（2026-07-13）

管理员已完成 3 项 Skill 升级，提交 commits `a8bc97b` + `d12d433`，VERSION 已 bump。

---

## 升级 1：vibe next 自动触发 vibe doctor

每次 `vibe next` 前自动跑 doctor，结果缓存 60 秒。有 violation 时先打印再输出建议。

---

## 升级 2：commit-msg hook 修复

vibe init 自动安装正确的 `commit-msg` hook（检查 `Vibe-Commit:` trailer）。
raw `git commit` 会被阻止，正确走 `vibe commit` 两步流程。

---

## 升级 3：spec amend 后自动检测 evidence digest 过期

**触发场景**：你修改 spec（review feedback 后 amend）后，已记录的 evidence 的 spec digest 不再匹配当前 spec，导致 `vibe advance` 报"缺少 evidence"。

**效果**：
- 现在 `vibe amend <project> <spec> "..." --apply` 执行完后，自动扫描关联 evidence
- 如果有 evidence 的 digest 已过期，输出 advisory：
  ```
  ⚠️  spec 'xxx' 已修改，以下 evidence 的 spec digest 已过期:
     - .agents/evidence/xxx/verify.md
     如果 evidence 内容仍然有效，请重新记录以刷新 digest
  ```
- 不影响流程（advisory only），只是提醒你

**对 Agent 的影响**：
- amend 后看到 advisory → 检查 evidence 是否仍有效
- 如果有效 → 重新 `vibe evidence ...` 记录一次（刷新 digest）
- 如果因 spec 修改已失效 → 修正后再记录
- 不用自己手动检查 digest 是否过期了

---

## 当前标准操作

```bash
# 初始化项目（自动装 commit-msg hook）
vibe init <path>

# 查看下一步（自动跑 doctor）
vibe next <project>

# 修改 spec（自动检测 evidence digest 过期）
vibe amend <project> <spec> "变更描述" --apply

# 提交代码（两步）
vibe commit <project>              # 看 diff
vibe commit --reviewed <project>   # verify + commit
```

---

## 已知限制

- evidence digest 过期只检测 `vibe amend`，不检测直接编辑 spec 文件的情况
- 只提示、不自动刷新（防止掩盖 evidence 失效问题）
- 592 个测试全部通过，升级安全
