# context-refresh-hardening

> 状态: done | 创建: 2026-06-13 20:41 UTC | 更新: 2026-06-13 20:44 UTC
> 类型: feature
> 风险: low
> 风险确认: confirmed
> 负责人: lance
> 依赖: 无
> 发布组: vibe-tooling

## 意图 (Intent)

**要解决什么问题？为谁解决？**

`self_analyze` 已经提示当前项目的上下文准确性存在改进空间。现有
`refresh_context.py` 主要依赖根目录配置文件，而且对 `AGENTS.md` 中的
“测试框架”等非加粗字段匹配不正确，导致像本仓库这种多子目录、弱配置的项目，
刷新后仍然大量保留“待确认”。需要增强它的保守检测能力和字段写回能力。

## 成功标准

- 对没有根级 `package.json/pyproject.toml` 的仓库，也能基于文件结构保守识别主要语言
- `refresh_context.py` 能正确更新 `AGENTS.md` 中的“测试框架”等非加粗字段
- 对已人工确认的值仍然只给建议，不强行覆盖

## 约束 (Constraints)

### 技术约束
- 只增强 `refresh_context.py` 及其测试，不修改 `AGENTS.md` 模板结构
- 检测逻辑必须保守，证据不足时保持“待确认”，不要臆测具体业务或部署方案

### 业务约束
- 生成结果仍然只能写项目本地 `AGENTS.md` 与 `.agents/context-refresh.md`
- 现有人工确认优先级高于自动检测

### 明确不做什么 (Out of Scope)
- 不自动补齐架构约束、安全要求或禁止事项的具体内容
- 不引入外部依赖或复杂索引器

## 验收标准 (Acceptance Criteria)

### 正常路径
1. 对多子目录 Python 仓库运行 `refresh_context.py`，能把语言/测试框架从“待确认”更新为保守结果
2. 已人工写死的字段若与检测结果不同，只记录到 `.agents/context-refresh.md`
3. 运行后 `当前阶段` 与 `最后更新` 仍会刷新

### 边界情况
- 根目录无配置文件但存在大量 `.py` 文件时，可识别为 Python
- 检测不到可靠测试信号时，测试框架保持原值，不强行填写

### 错误处理
- `AGENTS.md` 不存在时继续给出明确提示
- 遇到不可解析配置文件时，降级为结构扫描，不抛 traceback

## 非功能需求 (NFR)

### 性能
- 扫描限制在轻量级文件名与少量文件内容探测，不做全仓库深度解析
- 在当前仓库规模下应保持秒级完成

### 安全
- 只读取项目内常见元数据与源码文件，不执行项目代码
- 不把检测结果写到 Skill 内，只写项目本地上下文文件

### 可访问性 / 兼容性
- 继续保持 Python 3.10+ 兼容
- 兼容当前 `AGENTS.md` 模板中的加粗字段与普通字段格式

## 涉及范围

- **新增文件**: 无
- **修改文件**: vibe-coding-skill/scripts/refresh_context.py, vibe-coding-skill/tests/test_workflow.py
- **不动文件**: AGENTS.md 模板、self_analyze.py、self_upgrade.py

## 验证方式

- [ ] 相关回归测试已新增或更新
- [ ] 关键行为的验证路径已定义
- [ ] 手动验收通过（如无法自动化）
- [ ] 安全审查通过（如适用）
- [ ] 性能可接受（如适用）
