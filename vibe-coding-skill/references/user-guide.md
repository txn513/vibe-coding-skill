# Vibe Coding Skill — 自然语言速查手册

> @vibe-coding 之后，用以下任意一句话触发对应功能。
> 不需要记命令名，说人话就行。

---

## 一、项目接入

| 你说 | Skill 做什么 |
|---|---|
| `接入这个项目` | 扫描项目结构，初始化 `.agents/` 目录和 AGENTS.md |
| `这是新项目，帮我初始化` | 创建全新项目治理上下文 |
| `检查一下项目健康` | 运行 doctor，检查结构完整性、规范冲突、配置缺失 |
| `刷新上下文` | 更新 AGENTS.md 里的技术栈、当前阶段等项目信息 |
| `有哪些待确认的规范` | 列出接管老项目后尚未确认的规范差异 |

---

## 二、日常推进

| 你说 | Skill 做什么 |
|---|---|
| `下一步做什么` | 读取项目状态，告诉你当前最该做的一件事 |
| `检查状态` | 列出当前绑定项目路径、所有 spec 及其当前状态 |
| `这个功能做到哪了` | 查看当前 spec 的进度、证据、门禁情况 |
| `创建一个 spec：xxx` | 新建功能规格，引导你填写验收标准 |
| `帮我规划一下这个功能` | 创建 spec + 生成实施计划 |
| `创建 spec 时显示项目规则摘要` | create_spec 创建后自动列出 AGENTS.md 章节标题 + rules/*.md 文件标题,让 Agent 写 spec 时能引用 (候选 3 落地) |
| `生成计划` | 为当前 spec 生成任务分解计划 |
| `能推进到 review 吗` | 检查从 in-progress 到 review 的所有门禁 |
| `推进到 review` / `推进到 done` | 推进状态（会先检查门禁） |
| `跳过检查直接推进` | --force 推进（会记录强制原因） |
| `记录验证证据：xxx passed` | 记录 verify 阶段的证据 |
| `记录 evidence 并跑命令验证` | 必须 `--purpose` / `--configured` 放在 `--command` 之前,否则 fail-fast (record_evidence 强制顺序约束, Rule 36) |
| `通过审查` | 审查通过，推进到 released |
| `审查不通过，原因是 xxx` | 审查驳回，记录原因 |
| `生成 changelog` | 为已 released 的 spec 生成变更日志 |
| `有哪些 blocker` | 列出当前所有阻塞项 |

---

## 三、UI 设计与重设计

| 你说 | Skill 做什么 |
|---|---|
| `为这个前端需求生成 UI Design Contract` | 创建 `.agents/specs/<spec>/ui-design-contract.md`，把视觉意图转成可实现、可验收的合同 |
| `这是新前端项目，先做 UI 设计引导` | 在首个实现 spec 前先澄清产品意图、核心流程、页面结构、UI 状态和是否需要 UI Design Contract |
| `用 Open Design 为这个新项目探索 UI 方向` | 把 Open Design 作为项目级设计来源，要求输出落到项目本地，再转换成 UI Design Contract |
| `用 Open Design 先探索 UI，再生成 spec` | 先把 Open Design 输出治理化为 UI Design Contract，再创建对应实现 spec |
| `Open Design 怎么接入` | 读取 `references/adapters/opendesign.md`，按 daemon/CLI/MCP/API 检查清单接入 |
| `从 Open Design 结果生成 UI 合同` | 读取或引用 Open Design 产物，整理 source、layout、component map、states、UI-AC 和 evidence plan |
| `不要把 Open Design 推断成某套 UI 风格` | 明确 Open Design 只是设计来源；AGENTS.md 和项目视觉禁令优先 |
| `从 Penpot/Figma/截图整理 UI 合同` | 将外部设计工具或截图作为 source artifact，不直接当作验收标准 |
| `检查这个 UI spec 能不能交给纯文本模型实现` | 检查合同是否包含足够文本信息：tokens、layout、组件映射、状态、UI-AC |
| `基于当前 UI 设计继续迭代一版` | 自动按 Rule 42 版本化处理，不覆盖旧版；生成 v2/v3 设计修订并记录 changed/preserved/abandoned/rollback/AC impact/evidence update |
| `这版设计不要覆盖上一版` | 显式提醒版本化处理；必要时触发 amend 或 follow-up spec |
| `盘点当前项目 UI，准备重设计` | 先整理现有路由、页面、组件、状态、截图和关键路径 |
| `生成 UI Redesign Contract` | 创建 `.agents/specs/<spec>/ui-redesign-contract.md`，明确 preserve/replace 边界 |
| `用 Open Design 重设计当前 UI，但保留现有业务流程` | 先要求保留行为边界，再把设计探索转换成 UI Redesign Contract |
| `验证这个 UI 改动的视觉证据` | 检查截图、录屏、浏览器输出、Storybook capture 或 visual diff 是否映射到 UI-AC |

手动命令示例：

```bash
vibe ui-contract <spec> --source-type opendesign --source-artifacts design/opendesign/DESIGN.md --model-capability text-only
vibe ui-redesign-contract <spec> --source-type opendesign --source-artifacts design/opendesign/
```

---

## 四、Bug 修复

| 你说 | Skill 做什么 |
|---|---|
| `修一下 xxx bug` | 创建 bug spec，走复现→修复→回归完整流程 |
| `这个 bug 是回归问题` | 标记为回归，关联原始 spec |
| `记录复现证据` | 记录 bug 在修复前的复现证据 |
| `记录回归证据` | 记录修复后回归测试通过的证据 |
| `这个 bug 影响了哪些功能` | 查看依赖关系和影响范围 |

---

## 五、验收与复盘

| 你说 | Skill 做什么 |
|---|---|
| `验收一下 xxx 功能` | 对比 spec 验收标准与实际 evidence，输出差距报告 |
| `Vibe 复盘这个问题` | 自动定位最近完成的 spec，生成 retro + 结构化报告 |
| `复盘一下 xxx 功能` | 指定 spec 复盘 |
| `严格复盘: 复盘一下 xxx` | `vibe.py retrospective <root> <spec> --strict`, retro 缺 [复现命令/logcat/截图/unverified historical note] 任一 evidence 引用时 fail-fast (候选 2 落地, 默认仅 warning) |
| `分析一下项目改进点` | 扫描所有 retro，找重复失败模式和治理候选 |
| `有什么可以沉淀的吗` | 同上，分析历史回顾中的共性问题 |
| `发现 N 条 Skill 升级候选，是否应用？` | Agent 主动询问，你说 `应用` 才会修改 Skill |

---

## 六、规范与边界

| 你说 | Skill 做什么 |
|---|---|
| `检查规范冲突` | 对比 Skill 核心规则与项目本地规则，列出冲突 |
| `xxx 规范以项目为准` | 解决规范冲突，项目规则优先 |
| `这个项目的测试策略是什么` | 查看 `.agents/rules/testing.md` |
| `补充一下测试规则` | 帮你填写 testing.md 中的待确认项 |
| `这个功能涉及 fallback，验证一下` | 触发降级链路验证规则 |
| `这个功能涉及缓存过期，验证一下` | 触发 TTL/过期验证规则 |
| `这个治理源扫描器不识别, 我手动声明保留` | 跑 `vibe policy-override-add <root> <source_id> --reason "..." --actor <you>`, 把 `manifest_override: true` + reason + actor 写进 manifest + audit.md, doctor 不再报 missing warning |

---

## 七、多会话协作

| 你说 | Skill 做什么 |
|---|---|
| `上次做到哪了` | 读取 spec 状态、evidence、plan，汇报进度 |
| `继续上次的功能` | 定位最近的 in-progress spec，从断点继续 |
| `这个功能做了一半，帮我看看还差什么` | 对比 spec 验收标准，列出未完成项 |

---

## 八、Skill 自身

| 你说 | Skill 做什么 |
|---|---|
| `Skill 有哪些规则` | 列出 SKILL.md 中的核心规则 |
| `这个规则是什么意思` | 解释某条具体规则 |
| `Skill 有哪些辅助工具` | 列出 reviewer、debugger 等辅助 Skill |
| `安装辅助 Skill` | 运行 `vibe install-auxiliary --all` |

---

## 九、特殊场景

| 场景 | 你说 |
|---|---|
| 功能做了一半要切走 | `记录一下当前进度`（生成 evidence 快照） |
| 不确定风险等级 | `这个功能风险高吗`（Agent 会评估并建议） |
| 想修改已提交的 spec | `amend 一下这个 spec`（创建修订记录） |
| 想查看某个 spec 的审查记录 | `看一下 xxx 的审查` |
| 想查看某个 spec 的证据链 | `看一下 xxx 的证据` |
| 上下文可能过期了 | `刷新上下文`（更新 AGENTS.md） |
| `刷新 plan 上下文摘要` | 改了 adopted rules 或 AGENTS.md 后，运行 `vibe plan <spec> --refresh-context` |
| `改了 spec 之后 plan 怎么刷` | 改 spec frontmatter / 内容后，运行 `vibe plan <spec> --force`；`vibe next` 会按 stale 类型推荐命令 |
| 刚在多个项目间切换 | `下一步做什么` 或 `检查状态`（输出会显示当前绑定的项目路径） |
| 子 spec 拆分后不知道是否覆盖了原 spec | `核对一下原 spec 的意图`（触发意图对账） |
| 验证证据不够明确 | `这条证据对应哪条验收标准`（触发条款引用检查） |
| 依赖的 spec 还没做完 | `检查一下依赖`（触发依赖门禁检查） |

---

## 十、你不需要记的

以下事情 Skill 会自动做，不需要你手动触发：

- 推进状态前自动检查门禁（Rule 22）
- 推进后自动汇报状态（Rule 22）
- 运行 `下一步做什么`、`检查状态`、验收、复盘或推进前，自动绑定当前项目根目录；跨项目切换时不沿用上一个项目上下文（Rule 35）
- spec 已到 review/released/done 但 plan checkbox 进度明显滞后时，自动提示同步计划或记录移交/延期任务（Rule 22）
- Bug 修复自动要求复现+回归证据（Rule 10）
- 高风险变更自动要求观察证据（Rule 6）
- Out of Scope 项自动跟踪去向（Rule 26）
- 引入新存储位置的 spec 自动要求旧位置清理步骤（Rule 26 子规则）
- 验证自动要求用户可感知证据（Rule 28）
- 子 spec 全部 done 后自动要求父 spec 意图对账（Rule 29）
- 新 spec 模板自动使用 `AC1`、`AC2`... 显式验收标准编号（Rule 30）
- 记录 verify evidence 时会提示缺失的 AC 引用；medium/high 风险会被门禁检查 AC 覆盖（Rule 30）
- 重要操作前自动检查上下文是否过期（Rule 31）
- 依赖未完成的 spec 自动阻止进入实施（Rule 32）
- 切换任务前自动记录当前 spec 进度（Rule 33，你不需要说"先记一下"）
- 记录命令证据时，如果 `--purpose`/`--configured` 这类会改变证据语义的参数误放在 `--command` 后面，会直接报错并提示顺序（Rule 36）
- 复盘里的 Bug、失败行为或回归结论必须引用证据，或者标注为未复验历史观察（Rule 37）
- 创建 spec 后会显示项目规则来源，并立即输出 draft 校验报告（Rule 38）
- `下一步做什么` 会给出 vendor-neutral 的模型档位建议（lite/standard/strong/review）；具体模型可在项目配置中映射，不配置也能使用（Rule 39）
- UI 需求使用 Open Design、Penpot、Figma、截图或手写 brief 时，会先转换成项目本地 UI 合同；工具输出不能直接当成唯一需求或验收来源，也不能覆盖 AGENTS.md 或项目视觉禁令（Rule 40）
- 新的用户可见 UI 项目在首个实现 spec 前，会先提示产品/UX/UI 设计引导；你明确选择 code-first spike 或非 UI 项目时可以跳过（Rule 41）
- UI 设计反复修改时会自动版本化，不需要你额外说"不要覆盖旧版"；每版有版本号并保留回退目标，影响已计划/实施/验收的 spec 时会走 amend 或 follow-up spec（Rule 42）

---

## 十一、最省心的三句话

如果你只记三句，记这三句：

1. **`下一步做什么`** — 随时问，永远不会错
2. **`Vibe 复盘这个问题`** — 做完一个功能后说
3. **`验收一下 xxx`** — 不确定进度时说
