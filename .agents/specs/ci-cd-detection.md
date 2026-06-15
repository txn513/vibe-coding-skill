# ci-cd-detection

> 状态: done | 创建: 2026-06-13 21:48 UTC | 更新: 2026-06-13 21:49 UTC
> 类型: feature
> 风险: low
> 风险确认: confirmed
> 负责人: lance
> 依赖: 无
> 发布组: vibe-tooling

## 意图 (Intent)

**要解决什么问题？为谁解决？**

`refresh_context.py` 尚未检测 CI/CD 配置文件（GitHub Actions、GitLab CI、CircleCI、
Jenkinsfile 等），导致 AGENTS.md 的部署/CI 字段常为"待确认"。
在子目录增强后，这个缺口更明显——CI 配置是工程化成熟度的关键信号。

## 成功标准

- 能在有 `.github/workflows/` 的项目中检测到 GitHub Actions
- 能在有 `.gitlab-ci.yml` 的项目中检测到 GitLab CI
- 检测结果写入 AGENTS.md 的部署字段（或相关字段）

## 约束 (Constraints)

### 技术约束
- 只修改 `refresh_context.py` 及测试
- 只做文件存在性检测，不解析 YAML

### 业务约束
- 不把检测到的 CI 配置细节写入 Skill

### 明确不做什么
- 不解析 workflow 内容，不检测具体 job 配置
- 不检测自定义脚本型 CI（无标准配置文件的）

## 验收标准

### 正常路径
1. 有 `.github/workflows/*.yml` 时检测到 "GitHub Actions"
2. 有 `.gitlab-ci.yml` 时检测到 "GitLab CI"
3. 同时存在多个时合并报告

## 涉及范围

- **新增文件**: 无
- **修改文件**: vibe-coding-skill/scripts/refresh_context.py, vibe-coding-skill/tests/test_workflow.py
- **不动文件**: Skill 核心

## 验证方式

- [ ] 相关回归测试已新增或更新
- [ ] 关键行为的验证路径已定义
- [ ] 手动验收通过
- [ ] 安全审查通过
- [ ] 性能可接受
