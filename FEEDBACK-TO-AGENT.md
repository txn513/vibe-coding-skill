# 给 Agent 的反馈 — Skill 升级已完成（2026-07-13）

管理员已完成两项 Skill 升级，提交 commit `a8bc97b`，VERSION 已 bump。

## 升级 1：vibe next 自动触发 vibe doctor（方案 A）

**效果：**
- 每次运行 `vibe next` 前，系统**自动**跑一遍 `vibe doctor` 
- 如果有问题/警告，会先打印出来，再输出下一步建议
- 缓存 60 秒，连续调用不会重复跑
- 支持 `VIBE_QUIET_AUTO_DOCTOR=1` 静默模式（测试/CI 用）

**对 Agent 的影响：**
- 你不再需要手动跑 `vibe doctor` 来确认项目健康度
- 如果 doctor 报了 warning，你会在 `vibe next` 输出里直接看到
- 但不能因为 doctor 报 advisory 就跳过 `vibe next` 的建议——两者是串联关系

---

## 升级 2：commit-msg hook 修复（测试级修复）

**问题：** 之前 vibe init 安装的 hook 类型错误（pre-commit → commit-msg），导致所有 `git commit` 被错误拦截。

**修复：**
- 现在安装为正确的 `commit-msg` hook（检查 commit message 里的 `Vibe-Commit:` trailer）
- 新增环境变量 `VIBE_SKIP_COMMIT_MSG_HOOK=1`，测试/CI 可以跳过此检查

**对 Agent 的影响：**
- 新项目 init 后，`git commit` 不会触发 pre-commit hook 误报
- 但你仍然**必须用** `vibe commit` 提交代码（Rule 53 未变）
- 只有 `vibe commit` 写的 commit message 会带 `Vibe-Commit:` trailer

---

## 你现在的标准操作（更新后）

| 场景 | 操作 |
|------|------|
| 初始化新项目 | `vibe init <path>` → 自动装 commit-msg hook |
| 看下一步做什么 | `vibe next <project>` → **自动**跑 doctor |
| 提交代码 | 两步：`vibe commit`（看 diff）→ `vibe commit --reviewed`（verify + commit） |
| 跳过 commit hook | `VIBE_SKIP_COMMIT_MSG_HOOK=1 git commit ...`（仅测试/紧急用） |

---

## 注意

- 老项目的 commit-msg hook 不会自动更新，如需修复请手动：`rm .git/hooks/pre-commit && vibe install-precommit-hook .`
- 589 个测试全部通过，升级安全
