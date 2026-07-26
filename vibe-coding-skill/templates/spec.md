# {{SPEC_NAME}}

<!-- 状态合法值: draft / spec-ready / in-progress / review / released / done / blocked / cancelled / superseded -->
> 状态: {{STATUS}} | 创建: {{CREATED_AT}} | 更新: {{UPDATED_AT}}
> 类型: {{SPEC_TYPE}}
> 风险: {{RISK_LEVEL}}
> 风险确认: {{RISK_CONFIRMATION}}
> 负责人: {{OWNER}}
> 依赖: {{DEPENDENCIES}}
> 发布组: {{RELEASE_GROUP}}
> Prompt version: {{PROMPT_VERSION}}
{{REGRESSION_FROM_LINE}}
## 意图 (Intent)

**要解决什么问题？为谁解决？**

{{INTENT}}

## 成功标准

- {{SUCCESS_CRITERION_1}}
- {{SUCCESS_CRITERION_2}}
- {{SUCCESS_CRITERION_3}}

## 约束 (Constraints)

### 技术约束
- {{TECH_CONSTRAINT_1}}
- {{TECH_CONSTRAINT_2}}

### 业务约束
- {{BUSINESS_CONSTRAINT_1}}
- {{BUSINESS_CONSTRAINT_2}}

### 明确不做什么 (Out of Scope)
- [follow-up: spec-id] {{OUT_OF_SCOPE_1}}
- [abandoned] {{OUT_OF_SCOPE_2}}

## 验收标准 (Acceptance Criteria)

> 每条 AC 标注 [happy-path] 或 [degradation-path]。degradation-path AC 至少 1 条：失败/错误/降级/边界场景。

### 正常路径
1. AC1: {{HAPPY_PATH_1}}
2. AC2: {{HAPPY_PATH_2}}
3. AC3: {{HAPPY_PATH_3}}

### 边界情况
- AC4: {{EDGE_CASE_1}}
- AC5: {{EDGE_CASE_2}}

### 错误处理
- AC6: {{ERROR_HANDLING_1}}
- AC7: {{ERROR_HANDLING_2}}

## 非功能需求 (NFR)

### 性能
- {{PERFORMANCE_REQUIREMENT_1}}
- {{PERFORMANCE_REQUIREMENT_2}}

### 安全
- {{SECURITY_NFR_1}}
- {{SECURITY_NFR_2}}

### 可访问性 / 兼容性
- {{ACCESSIBILITY_REQUIREMENT_1}}
- {{ACCESSIBILITY_REQUIREMENT_2}}

## 涉及范围

- **新增文件**: {{NEW_FILES}}
- **修改文件**: {{MODIFIED_FILES}}
- **不动文件**: {{DO_NOT_TOUCH}}
- **受影响的读路径**: {{READ_PATH_IMPACT}}
  > Rule 44: 如果本 spec 引入写操作 / 状态变更 / 新存储位置，必须列出可能被影响的读路径，或显式标注「无读路径影响」并给出一行原因。留空或跳过均视为不通过 spec-ready 门禁。

{{FIX_SCOPE_SECTION}}{{CALL_SITES_SECTION}}
## 文档更新 (R-D-87)

完成后必填 (与 R-D-72 evidence 并列):
- [ ] 更新 docs/modules/<本 spec 涉及的主要模块>.md (职责 / API / 关键文件 / 坑点)
- [ ] 如改了技术栈 / 新增依赖, 更新 docs/tech-stack.md
- [ ] 如引入新决策, 写 adr/000N-<slug>.md
- [ ] 如改了架构边界 / 引入新服务, 更新 docs/architecture.md
- [ ] 如发现新业务术语, 更新 docs/glossary.md
- [ ] 如完成 spec 影响 docs/README.md 索引, 同步更新

> Rule R-D-87: 项目文档纪律. docs/ 是跨 session 的项目知识,
> 让下一个 agent (或 compact 后恢复) 能快速进入状态.
> v0.1 软门禁 — doctor 报 stale 但不阻塞 advance.

## 验证方式

### 正常路径 (Happy Path)
- [ ] 相关回归测试已新增或更新
- [ ] 关键行为的验证路径已定义
- [ ] 手动验收通过（如无法自动化）
- [ ] 安全审查通过（如适用）
- [ ] 性能可接受（如适用）

### 降级路径 (Degradation Path)
> 如果 spec 涉及降级、失败 fallback、异常处理等场景，必须在此验证。
> 如果无降级场景，写 "N/A" 并说明原因。

- [ ] 失败场景: <描述失败条件>
- [ ] 降级行为: <描述 fallback 行为>
- [ ] 用户感知: <toast / 404 / 默认值 / 重试 / ...>
- [ ] 验证证据: <evidence 文件路径或 test 引用>
