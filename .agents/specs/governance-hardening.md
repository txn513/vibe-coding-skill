# governance-hardening

> 状态: done | 创建: 2026-06-13 14:00 UTC | 更新: 2026-06-13 14:33 UTC
> 类型: feature
> 风险: medium
> 风险确认: confirmed
> 负责人: lance
> 依赖: 无
> 发布组: vibe-tooling

## 意图 (Intent)

加强现有治理承诺的执行力，使 Bug 双向证据、项目规则生命周期和需求变更后的风险重评成为机器可检查的门禁。

## 成功标准

- Bug 进入 review 前需要复现与修复回归两类证据
- proposed 项目规则不会进入执行 Prompt
- amendment 后必须重新确认风险才能进入 spec-ready

## 约束 (Constraints)

### 技术约束
- 保持现有项目兼容，旧规则默认 adopted
- 不引入第三方依赖

### 业务约束
- 只实现通用治理机制

### 明确不做什么 (Out of Scope)
- 不写入具体业务、框架或安全答案
- 不编排外部部署与监控系统

## 验收标准 (Acceptance Criteria)

### 正常路径
1. Bug 双向证据满足后可进入 review
2. proposed 规则被 Prompt 排除，adopted 规则被包含
3. amendment 后风险确认变为 pending，重新确认后可继续

### 边界情况
- 旧项目规则无状态元数据时保持有效
- 修复前复现证据不因源码修复而失效

### 错误处理
- 非法规则状态、证据用途和风险等级被拒绝

## 非功能需求 (NFR)

### 性能
- 治理检查保持本地毫秒级

### 安全
- 不执行 shell 字符串，不降低现有证据脱敏能力

### 可访问性 / 兼容性
- 支持现有 Python 版本和 Codex/Trae 共用安装方式

## 涉及范围

- **新增文件**: scripts/rule_status.py, scripts/confirm_risk.py
- **修改文件**: workflow、evidence、prompt、doctor、dispatcher、tests 和文档
- **不动文件**: 具体项目业务实现

## 验证方式

- [ ] 全量单元测试通过
- [ ] Skill 校验通过
- [ ] Skill 边界审计通过
