# changelog-auto-on-release

> 状态: done | 创建: 2026-06-14 09:50 UTC | 更新: 2026-06-14 09:58 UTC
> 类型: refactor
> 风险: medium
> 风险确认: confirmed
> 负责人: lance
> 依赖: 无
> 发布组: vibe-coding-suite

## 意图 (Intent)

**要解决什么问题？为谁解决？**

`generate_changelog.py` 已存在且被验证可用，但只在 `vibe changelog` 显式调用时才跑。`vibe advance ... released` 状态推进成功后，**没有任何机制**自动留 changelog 痕迹——上一轮 `suite-auxiliary-onboarding` 推进到 `released` 时，我手动跑了 `vibe changelog`；这是流程缺口。

**重构目标**: 让 `vibe advance ... released` 成功后自动调 `generate_changelog`；非交互场景支持跳过；不改变现有 `vibe changelog` 行为。

**当前问题**: 
- 状态推进到 `released` 的人为 chokepoint 缺自动化兜底
- 漏跑 changelog 时无法从 `.agents/` 状态中反推——只有时间戳和 evidence 留下

**预期改善**:
- `vibe advance ... released` 默认在状态写完后自动跑 changelog，路径打印到 stdout
- 显式 `--skip-changelog` 可关闭（CI、批量状态推进、纯脚本场景）
- 显式 `--changelog-version vX.Y.Z` 可指定版本号（默认按时间戳 `unreleased-YYYYMMDD-HHMMSS`，避免同日多次发布覆盖）
- 已有 `vibe changelog` 命令行为不变

## 成功标准

- `vibe advance <project> <spec> released` 成功后，stdout 包含形如 `📝 已生成 changelog: .agents/changelogs/CHANGELOG-unreleased-YYYYMMDD-HHMMSS.md` 的行
- 同一个 spec 跑两次 advance released，第二次的 changelog 文件名不同（时间戳后缀），互不覆盖
- `vibe advance ... released --skip-changelog` 状态下不调用 `generate_changelog`
- `vibe advance ... released --changelog-version v1.2.0` 状态下生成 `CHANGELOG-v1.2.0.md`
- 已有 75 个测试全过；新增 ≥ 3 个新测试覆盖自动 / 跳过 / 版本三个分支

## 约束 (Constraints)

### 技术约束
- 不修改 `generate_changelog.py` 本身；它是已就位的被调用方
- 不修改 `vibe changelog` 子命令的现有行为
- 修改只发生在 `set_status.py` 的 released 分支末尾 + `vibe.py` 的 `advance` 子命令参数

### 业务约束
- 时间戳版本号的格式为 `unreleased-YYYYMMDD-HHMMSS`（UTC），与现有 `unreleased` 默认值前缀一致
- 自动生成失败时**不阻塞**状态推进（已写文件、已记录 activity），仅 stderr 警告

### 明确不做什么 (Out of Scope)
- 不自动 bump 项目的真实版本号（项目没有"版本号"概念时的副作用）
- 不在 `done` 状态也跑（`done` 可以是观察期后重做，不一定对应新发布）
- 不改 `vibe changelog` 现有签名

## 验收标准 (Acceptance Criteria)

### 正常路径
1. `vibe advance . <spec> released` 状态成功推进，stdout 出现 `📝 已生成 changelog:` 行，文件落到 `.agents/changelogs/`
2. 文件名匹配 `CHANGELOG-unreleased-YYYYMMDD-HHMMSS.md`
3. 同一 spec 第二次推进时，新文件不覆盖旧文件（文件名不同）

### 边界情况
- 自动 changelog 因 `generate_changelog` 抛异常失败：状态推进已成功，不回滚；stderr 出现 `⚠️  自动 changelog 失败:` 行
- `--changelog-version` 与 generate_changelog 的版本号语义保持一致：空字符串走默认时间戳，传入 `vX.Y.Z` 走显式版本

### 错误处理
- 状态推进本身失败时（如缺 review 证据），不应进入 changelog 调用分支
- 强制推进 `--force` 模式不触发 changelog（用户主动跳过流程时，不应偷偷补留档）

## 非功能需求 (NFR)

### 性能
- changelog 生成时间 < 2s（与现有 `vibe changelog` 性能一致）
- 不引入新的 I/O 路径

### 安全
- 生成的 changelog 路径仍在 `.agents/changelogs/` 内，不写工作区其他位置
- 异常时不传播栈到 stdout（仅 stderr 单行警告）

### 可访问性 / 兼容性
- Python 3.10+；仅标准库
- 已有 Unix shell 行为不变

## 涉及范围

- **新增文件**: 无
- **修改文件**: `vibe-coding-skill/scripts/set_status.py`（+25 行：新增 `changelog_version` / `auto_changelog` 参数 + released 分支末尾调用）、`vibe-coding-skill/scripts/vibe.py`（+10 行：advance 子命令新增 `--changelog-version` 与 `--skip-changelog` 参数，转发给 set_status）、`vibe-coding-skill/tests/test_workflow.py`（+80 行：3-4 个新测试）、`vibe-cli/src/main.py`（+8 行：转发新参数）
- **不动文件**: `vibe-coding-skill/scripts/generate_changelog.py`、`vibe-coding-skill/SKILL.md`、`vibe-coding-reviewer/`（本次重构不涉及辅助 Skill）

## 验证方式

- [ ] 边界审计通过：`vibe boundary . --skill-root vibe-coding-skill` 报告 0 违规
- [ ] 既有 75 个测试全过
- [ ] 新增测试覆盖：自动 / skip / 显式版本 / 失败兜底
- [ ] 手动验证：在当前项目上跑 `vibe advance . suite-auxiliary-onboarding released` 不会改状态（已 done），所以改用 `vibe advance . <新建测试 spec> released` 验证

## 风险确认记录

- (待确认)

## 风险确认记录

- 2026-06-14 09:52 UTC: medium → medium — Refactor only: add auto-changelog hook to existing released transition. No business rules added; no existing behavior removed (vibe changelog command still callable standalone). Failure of changelog does not block the status write, so risk is contained to a stderr warning.
