# context-refresh-command

> 状态: done | 创建: 2026-06-13 20:47 UTC | 更新: 2026-06-13 20:48 UTC
> 类型: feature
> 风险: low
> 风险确认: confirmed
> 负责人: lance
> 依赖: 无
> 发布组: vibe-tooling

## 意图 (Intent)

**要解决什么问题？为谁解决？**

虽然 `refresh_context.py` 已经具备保守刷新 `AGENTS.md` 的能力，但用户仍需直接调
脚本，和已经统一的 `spec/plan/review/retro` 入口不一致。需要提供
`vibe context-refresh`，让项目上下文刷新也进入统一 CLI。

## 成功标准

- `vibe context-refresh` 能成功调用 `refresh_context.py`
- `vibe --help` 与 README 显示 `context-refresh`
- 当前项目执行 `vibe context-refresh` 时，能正常刷新或报告“上下文已是最新”

## 约束 (Constraints)

### 技术约束
- 继续沿用 `refresh_context.py`，CLI 和 dispatcher 只做转发
- 不复制上下文检测逻辑到 CLI

### 业务约束
- 只更新项目本地 `AGENTS.md` 与 `.agents/context-refresh.md`
- 不改变 `refresh_context.py` 既有保守边界

### 明确不做什么 (Out of Scope)
- 不新增新的上下文检测能力
- 不修改 `AGENTS.md` 模板结构

## 验收标准 (Acceptance Criteria)

### 正常路径
1. `vibe --help` 显示 `context-refresh`
2. `vibe context-refresh` 成功执行并输出刷新结果
3. 当前项目执行后不会报 traceback，且 AGENTS.md 仍保持可读

### 边界情况
- 当上下文已是最新时，命令输出“无需变更”
- 当存在人工确认值时，沿用 `refresh_context.py` 的人工核对提示

### 错误处理
- 如果 Skill 脚本路径缺失，沿用现有 CLI 的脚本定位错误提示
- 缺少命令参数时，保留 argparse 标准帮助输出

## 非功能需求 (NFR)

### 性能
- 命令启动成本与现有 `doctor/review/retro` 同量级
- 不增加额外进程层级，仍由一次 CLI 转发完成

### 安全
- 不新增依赖，不扩大写入边界
- 不执行项目代码，只调用既有上下文刷新脚本

### 可访问性 / 兼容性
- 保持 Python 3.10+ 兼容
- 命令名与现有 `status/next/doctor/retro` 风格一致

## 涉及范围

- **新增文件**: 无
- **修改文件**: vibe-cli/src/main.py, vibe-cli/README.md, vibe-coding-skill/scripts/vibe.py, vibe-coding-skill/tests/test_workflow.py
- **不动文件**: vibe-coding-skill/scripts/refresh_context.py, AGENTS.md 模板

## 验证方式

- [ ] 相关回归测试已新增或更新
- [ ] 关键行为的验证路径已定义
- [ ] 手动验收通过（如无法自动化）
- [ ] 安全审查通过（如适用）
- [ ] 性能可接受（如适用）
