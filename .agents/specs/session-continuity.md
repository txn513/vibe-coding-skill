# session-continuity

> 状态: done | 创建: 2026-06-14 05:00 UTC | 更新: 2026-06-14 07:58 UTC
> 类型: feature
> 风险: low
> 风险确认: confirmed
> 负责人: lance
> 依赖: 无
> 发布组: vibe-tooling

## 意图 (Intent)

**要解决什么问题？为谁解决？**

当前 `vibe next` 在所有 Spec 都 done 后只输出"创建或选择下一个工作项"，是冷启动。
用户隔几天回来时，更想看到"你上次在做 X，要继续吗？"这种会话连续性提示。

需要让 `recommend_next` 在没有活跃 Spec 时，基于"上次活动"判断：
- 是否有最近动过但还没完成的 Spec
- 是否有长期未推进的 in-progress Spec（"卡住了吗？"）
- 最近完成的是哪个 Spec（"你最后交付的是 X"）

## 成功标准

- `recommend_next` 在"无活跃工作"分支里能输出"继续 {name}"或"X 已经 N 天没动"建议
- 不修改 Spec 现有 front matter 字段，只读取 `> 更新:` 时间戳
- 不影响已有门禁判断

## 约束 (Constraints)

### 技术约束
- 只读不写：只读取 Spec front matter 的 `更新:` 字段，不新增字段
- 只在 `recommend_next` 的"无活跃工作"分支中生效

### 业务约束
- 不记录用户身份/会话信息到 Skill 本体
- 不影响其他推荐分支的优先级

### 明确不做什么
- 不实现真正的锁或会话状态文件
- 不持久化"用户上次在做什么"为长期会话文件
- 不跨项目记忆（每个项目独立）

## 验收标准 (Acceptance Criteria)

### 正常路径
1. 有最近 7 天内动过的 in-progress Spec：next 输出"继续 {name}"
2. 有超过 7 天未动的 in-progress Spec：next 输出"{name} 已经 N 天没动，继续还是关闭？"
3. 所有 Spec 都是 done 但最近有刚完成的：next 提示"上次完成的是 {name}"

### 边界情况
- Spec 没有 `更新:` 字段：跳过
- 时间戳无法解析：跳过该 Spec，不抛 traceback
- 没有 Spec：保持现有"初始化"提示

## 非功能需求 (NFR)

### 性能
- 只读取已有 Spec 文件，不新增 IO

### 安全
- 不修改任何文件

## 涉及范围

- **新增文件**: 无
- **修改文件**: vibe-coding-skill/scripts/workflow_state.py, vibe-coding-skill/scripts/project_status.py, vibe-coding-skill/tests/test_workflow.py
- **不动文件**: Skill 核心边界规则、项目业务文件

## 验证方式

- [ ] 相关回归测试已新增或更新
- [ ] 关键行为的验证路径已定义
- [ ] 手动验收通过
