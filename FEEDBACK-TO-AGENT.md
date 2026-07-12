# 给 Agent 的反馈 — Skill 升级已完成（2026-07-13）

管理员已完成 4 项 Skill 升级，commits `a8bc97b` → `d12d433` → `365025e`。

---

## 升级 1：vibe next 自动触发 vibe doctor

**效果：**
- 每次运行 `vibe next` 前，系统**自动**跑一遍 `vibe doctor`
- 如果有问题/警告，会先打印出来，再输出下一步建议
- 缓存 60 秒，连续调用不会重复跑
- 支持 `VIBE_QUIET_AUTO_DOCTOR=1` 静默模式（测试/CI 用）

---

## 升级 2：commit-msg hook 修复

vibe init 自动安装正确的 `commit-msg` hook（检查 `Vibe-Commit:` trailer）。
raw `git commit` 会被阻止，正确走 `vibe commit` 两步流程。

---

## 升级 3：spec amend 后自动检测 evidence digest 过期

**效果：**
- `vibe amend <project> <spec> "..." --apply` 执行完后，自动扫描关联 evidence
- 如果有 evidence 的 digest 已过期，输出 advisory：
  ```
  ⚠️  spec 'xxx' 已修改，以下 evidence 的 spec digest 已过期:
     - .agents/evidence/xxx/verify.md
     如果 evidence 内容仍然有效，请重新记录以刷新 digest
  ```
- advisory only，不阻塞流程

---

## 升级 4：Skill 升级候选提案标准化工作流（**重点**）

### 问题
之前 Agent 不知道把跨项目的治理改进写到哪，导致 retro 里提了很多 Skill 候选但没有统一归档。

### 解决方案
**新增 `vibe propose-skill-upgrade` 命令**，标准化提案创建 + 检测 + 归档流程。

### 标准操作

```bash
# 发现可跨项目复用的治理改进 → 创建提案
vibe propose-skill-upgrade <project> "<标题>"
# 例：vibe propose-skill-upgrade . "evidence digest stale auto-detection"

# 会自动创建 .agents/skill-upgrade-candidates/skill-upgrade-candidate-YYYYMMDD.md
# 同一天多个提案自动加后缀 b, c, d

# 填好提案内容（问题/方案/通用性审计）后提交给管理员

# 管理员评审后归档
mv .agents/skill-upgrade-candidates/xxx.md \
   .agents/archive/skill-upgrade-candidates/
```

### vibe next 自动检测
- 如果项目有未归档的提案，`vibe next` 会输出 advisory 提醒管理员评审
- 归档后自动静默

### retro.md 模板已更新
"沉淀落点"段新增指引：
> 如果 retro 发现可跨项目复用的治理改进，**必须**写入 `.agents/skill-upgrade-candidates/`

### 提案文件模板结构

```markdown
# Skill 升级候选 — YYYYMMDD

来源: （retro 文件名）
日期: 
标题: 
状态: proposed

---

## 候选 1: （标题）

**分类**: governance / project

**问题**: （现象 + 引用 retro/实际案例）

**建议方案**: （Skill 规则变更 / 新增命令 / 流程调整）

**通用性审计**:
- 通用: （是/否，跨项目适用？）
- 不含项目知识: （是/否）
- 失败模式: （"rule exists but not bound to a gate" 等）

**影响范围**: （哪些 agent 行为会受影响）

**实施复杂度**: 低 / 中 / 高

**预期收益**: 

---

## 评估

| 候选 | 紧急程度 | 实施复杂度 | 预计收益 |
|------|---------|-----------|---------|
| 候选 1 | 高/中/低 | 低/中/高 | ... |

建议优先级: （排序）

---

## 管理员反馈

（待管理员评审后填写）
```

---

## 当前完整标准操作

```bash
# 初始化项目（自动装 commit-msg hook）
vibe init <path>

# 查看下一步（自动跑 doctor + 检测未归档提案）
vibe next <project>

# 创建 skill 升级候选提案
vibe propose-skill-upgrade <project> "<标题>"

# 修改 spec（自动检测 evidence digest 过期）
vibe amend <project> <spec> "变更描述" --apply

# 提交代码（两步）
vibe commit <project>              # 看 diff
vibe commit --reviewed <project>   # verify + commit
```

---

## 测试状态

- 595 个测试全部通过
- VERSION: `365025e-propose-skill-upgrade-command`
