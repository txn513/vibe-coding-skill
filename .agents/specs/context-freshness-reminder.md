# context-freshness-reminder

> 状态: done | 创建: 2026-06-13 21:03 UTC | 更新: 2026-06-13 21:07 UTC
> 类型: feature
> 风险: low
> 风险确认: confirmed
> 负责人: lance
> 依赖: 无
> 发布组: vibe-tooling

## 意图 (Intent)

**要解决什么问题？为谁解决？**

当前工作流已经能刷新 `AGENTS.md`，但还不能在“上下文已经明显变旧”时主动提醒。
这样会导致用户问“下一步做什么”时，系统继续依据过期上下文推进，而不是先提示刷新。
需要增加一个轻量的上下文新鲜度治理能力，让 `doctor` 和 `next` 都能识别：

- `AGENTS.md` 缺少 `最后更新`
- `AGENTS.md` 时间戳过旧
- 项目内已经存在 `.agents/context-refresh.md`，说明有待人工确认项

这个能力只负责发现和提醒，不自动改项目业务内容。

## 成功标准

- `doctor_project.py` 能在上下文过期或待人工确认时给出 warning
- `project_status.recommend_next()` 在上下文明显过期时优先建议先刷新项目上下文
- 新提醒不影响已有工作流门禁判断，也不制造项目特定知识

## 约束 (Constraints)

### 技术约束
- 只在现有治理脚本内增加轻量检测，不引入新存储结构
- 优先复用 `AGENTS.md` 的 `最后更新` 字段和现有 `.agents/context-refresh.md`

### 业务约束
- 只输出治理层提醒，不自动覆盖人工确认过的项目信息
- 不把任何业务规则、认证语义、测试案例内容写入 Skill 核心

### 明确不做什么 (Out of Scope)
- 不实现定时任务、后台 watcher 或自动修复
- 不因为上下文过期就阻断整个工作流，只做提醒和下一步优先级调整

## 验收标准 (Acceptance Criteria)

### 正常路径
1. 当 `AGENTS.md` 的 `最后更新` 超过阈值时，`doctor` 输出上下文过期 warning
2. 当存在 `.agents/context-refresh.md` 时，`doctor` 输出待人工确认 warning
3. 当上下文过期时，`recommend_next()` 返回“先刷新项目上下文”作为主建议

### 边界情况
- 如果 `AGENTS.md` 没有 `最后更新` 字段，也能给出明确提醒
- 如果没有任何 Spec，仍可优先提示先刷新上下文再继续判断下一步

### 错误处理
- 时间戳格式异常时不抛 traceback，而是退化为 warning
- 没有 `.agents/` 或 `AGENTS.md` 时，保持现有未初始化提示

## 非功能需求 (NFR)

### 性能
- 只读取少量项目元数据文件，保持秒级输出
- 不扫描完整 Git 历史或大范围文件 diff

### 安全
- 只读取项目本地治理文件，不执行项目代码
- 不自动修改业务代码或项目规则

### 可访问性 / 兼容性
- 保持 Python 3.10+ 兼容
- 继续兼容当前 `AGENTS.md` 模板格式

## 涉及范围

- **新增文件**: 无
- **修改文件**: vibe-coding-skill/scripts/common.py, vibe-coding-skill/scripts/doctor_project.py, vibe-coding-skill/scripts/project_status.py, vibe-coding-skill/scripts/refresh_context.py, vibe-coding-skill/tests/test_workflow.py
- **不动文件**: Skill 核心边界规则、项目业务文件

## 验证方式

- [x] 相关回归测试已新增或更新
- [x] 关键行为的验证路径已定义
- [x] 手动验收通过（如无法自动化）
- [x] 安全审查通过（如适用）
- [x] 性能可接受（如适用）
