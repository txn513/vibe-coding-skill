# retro-command

> 状态: done | 创建: 2026-06-13 20:29 UTC | 更新: 2026-06-13 20:32 UTC
> 类型: feature
> 风险: low
> 风险确认: confirmed
> 负责人: lance
> 依赖: 无
> 发布组: vibe-tooling

## 意图 (Intent)

**要解决什么问题？为谁解决？**

目前创建回顾仍需直接运行 `vibe-coding-skill/scripts/create_retro.py`，这让
`vibe-cli` 在工作流最后一步出现了断裂。需要提供统一入口 `vibe retro <spec>`，
让用户可以和 `spec/plan/review/evidence` 一样，通过同一 CLI 完成回顾创建。

## 成功标准

- `vibe retro <done-spec>` 能创建 `.agents/retros/<spec>.md`
- 对非 `done` 规格运行 `vibe retro <spec>` 时，保留现有门禁并给出明确提示
- `vibe --help` 与 README 都显示 `retro` 命令

## 约束 (Constraints)

### 技术约束
- 优先沿用 `vibe-coding-skill/scripts/create_retro.py`，不要在 CLI 中复制模板逻辑
- 保持 `vibe-cli` 与 `vibe.py` 的命令面一致，避免 CLI 和 dispatcher 分叉

### 业务约束
- 回顾仍然只允许针对 `done` 规格创建
- 现有 `.agents/retros/` 结构与模板不变

### 明确不做什么 (Out of Scope)
- 不修改回顾模板内容
- 不改变 `self_analyze` / `self_prune` 的输入结构

## 验收标准 (Acceptance Criteria)

### 正常路径
1. 对已完成规格执行 `vibe retro cli-sync`，创建或复用 `.agents/retros/cli-sync.md`
2. `vibe --help` 显示 `retro`
3. README 的命令列表与工作流示例包含 `retro`

### 边界情况
- 对未完成规格执行 `vibe retro retro-command`，返回“只有状态为 done 的规格才能创建回顾”
- 对已存在回顾的规格再次执行 `vibe retro cli-sync`，返回已存在提示而不是覆盖文件

### 错误处理
- 缺少规格名时，保留 argparse 标准错误输出
- 如果 Skill 脚本路径缺失，沿用现有 CLI 的脚本定位错误提示

## 非功能需求 (NFR)

### 性能
- 命令启动方式与现有 `review/prompt/doctor` 一致，不新增明显等待
- 不新增额外进程链路，仍由单次 CLI 转发完成

### 安全
- 不新增依赖，不扩大文件写入范围，只写目标回顾文件
- 不绕过 `done` 状态门禁

### 可访问性 / 兼容性
- 保持 Python 3.10+ 兼容
- 命令名与现有 CLI 风格保持一致，便于记忆与发现

## 涉及范围

- **新增文件**: 无
- **修改文件**: vibe-cli/src/main.py, vibe-cli/README.md, vibe-coding-skill/scripts/vibe.py
- **不动文件**: vibe-coding-skill/scripts/create_retro.py, .agents/retros/*.md, 回顾模板文件

## 验证方式

- [ ] 相关回归测试已新增或更新
- [ ] 关键行为的验证路径已定义
- [ ] 手动验收通过（如无法自动化）
- [ ] 安全审查通过（如适用）
- [ ] 性能可接受（如适用）
