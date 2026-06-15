# cli-sync

> 状态: done | 创建: 2026-06-12 23:20 UTC | 更新: 2026-06-13 20:24 UTC
> 类型: feature
> 风险: low
> 负责人: lance
> 依赖: 无
> 发布组: vibe-tooling

## 意图 (Intent)

**要解决什么问题？为谁解决？**

vibe-cli 目前只封装了早期 6 个命令（init、spec、specs、plan、check、review），
但 vibe-coding-skill 的 scripts/ 已扩展到 28 个脚本，包含 doctor、migrate、
next、evidence、record-review、self-analyze、self-upgrade、self-prune 等能力。
CLI 需要同步覆盖所有现有脚本，让用户通过统一的 vibe <command> 入口使用
完整工作流，而不是被迫区分 CLI 和直接调 Python 脚本。

## 成功标准

- vibe next 输出一个门禁感知的优先级建议，含原因和阻塞信息
- vibe status 显示项目全局状态概览
- vibe doctor 诊断工作流完整性并报告问题
- vibe migrate --apply 无损迁移旧版工作流元数据
- vibe evidence <spec> verify passed --command <cmd> 执行真实命令并记录证据
- vibe evidence <spec> verify passed --configured 执行项目配置的所有命令
- vibe advance <spec> <status> 推进 Spec 状态并执行门禁检查
- vibe amend <spec> <desc> 记录需求变更并归档过期产物
- vibe review <spec> --reviewer NAME 生成审查上下文
- vibe review-decision <spec> approved <basis> <evidence> --reviewer NAME 提交结构化结论
- 现有 vibe init、vibe spec、vibe plan、vibe check 行为不变
- README.md 更新为与实现一致的命令列表

## 约束 (Constraints)

### 技术约束
- CLI 只是薄封装层，所有逻辑委托给 vibe-coding-skill/scripts/ 中的脚本
- 不复制业务逻辑到 CLI，不创建第二套状态机
- 保持零第三方依赖（当前 CLI 只用 stdlib）

### 业务约束
- README.md 文档必须与实现一致
- 命令名称与 vibe.py 子命令保持一致

### 明确不做什么 (Out of Scope)
- 不修改 vibe-coding-skill/ 中的任何脚本
- 不新增 Script（CLI 只做转发）
- 不修改 .agents/ 的数据结构

## 验收标准 (Acceptance Criteria)

### 正常路径
1. 在已初始化项目中运行 vibe next，输出一条优先建议及原因
2. 运行 vibe status，输出项目阶段、Spec 列表和下一步建议
3. 运行 vibe doctor，输出 schema 版本、迁移状态和完整性问题
4. 运行 vibe evidence cli-sync verify passed --command echo ok，生成证据文件且含 Exit: 0
5. 运行 vibe advance cli-sync spec-ready，将本 Spec 从 draft 推进到 spec-ready
6. 运行 vibe review cli-sync --reviewer test，生成审查上下文文件
7. 运行 vibe review-decision cli-sync approved "looks good" "checked" --reviewer test，更新审查决策

### 边界情况
- 在未初始化的项目中运行 vibe next，提示接入或初始化
- 对不存在的 Spec 运行 vibe advance，返回错误
- vibe evidence 缺少 --command 且 --configured 时项目未配置命令，返回错误

### 错误处理
- 所有命令在项目未初始化时给出明确提示而非 Python traceback
- 参数缺失时给出 argparse 的标准错误输出

## 非功能需求 (NFR)

### 性能
- 所有命令在 2 秒内启动并开始输出（CLI 本身无重计算）

### 安全
- 不记录或缓存任何参数到磁盘
- evidence --command 的输出由 skill 脚本负责脱敏

### 可访问性 / 兼容性
- 支持 Python 3.10+

## 涉及范围

- **新增文件**: 无（所有逻辑通过修改 main.py 的子命令实现）
- **修改文件**: vibe-cli/src/main.py, vibe-cli/README.md
- **不动文件**: vibe-coding-skill/, vibe-cli/src/check.py, vibe-cli/src/scaffold.py, vibe-cli/src/spec.py, vibe-cli/src/plan.py, vibe-cli/src/review.py

## 验证方式

- [ ] vibe next 在未初始化项目中正确提示
- [ ] vibe status 在已初始化项目中输出阶段信息
- [ ] vibe doctor 检测 schema 版本和依赖循环
- [ ] vibe advance cli-sync spec-ready 成功推进
- [ ] vibe evidence 记录真实命令退出码
- [ ] vibe review-decision 写入 Decision-Record 标记
