# {{SPEC_NAME}}

> 状态: {{STATUS}} | 创建: {{CREATED_AT}} | 更新: {{UPDATED_AT}}
> 类型: {{SPEC_TYPE}}
> 风险: {{RISK_LEVEL}}
> 风险确认: {{RISK_CONFIRMATION}}
> 负责人: {{OWNER}}
> 依赖: {{DEPENDENCIES}}
> 发布组: {{RELEASE_GROUP}}
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

## 验证方式

- [ ] 相关回归测试已新增或更新
- [ ] 关键行为的验证路径已定义
- [ ] 手动验收通过（如无法自动化）
- [ ] 安全审查通过（如适用）
- [ ] 性能可接受（如适用）
