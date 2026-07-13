# 给 Agent 的反馈 — Skill 升级已完成（2026-07-13）

管理员已评审候选：`skill-upgrade-candidate-20260712.md`（OAuth credential in URL query AST 扫描）

**候选已归档**: `.agents/archive/skill-upgrade-candidates/skill-upgrade-candidate-20260712.md`

---

## 候选处理结果

**状态**: 已采纳 ✅

**Commit**: `5ec3b1b` — feat(skill): add OAuth credential-in-URL security scanner (RFC 6749)
**VERSION**: `5ec3b1b-oauth-credential-in-url-security-scan`

---

## 为什么采纳

| 维度 | 评估 |
|------|------|
| 问题真实性 | ✅ 妙藏项目已踩坑，有 retro 实证 |
| 通用性 | ✅ RFC 6749 标准，跨项目适用 |
| 不含项目知识 | ✅ 字段名是 OAuth 协议常量 |
| 项目级已有 | ✅ `scripts/r2_oauth_scan.py` 可参考 |
| 误报风险 | 低（`client_id` 白名单，7 处已知例外） |

---

## 改了什么

### 1. 新增 `vibe security-scan` 命令

```bash
vibe security-scan <project>        # 扫描 OAuth credential 泄露
vibe security-scan <project> --fix  # 自动修复（预留）
```

### 2. `scripts/security_scan.py` — OAuth credential 泄露检测

**检测逻辑**：
- AST 扫描 `Call(func=Attribute(attr='post'), keywords=[keyword(arg='params', value=Dict)])`
- 匹配敏感字段：`client_secret`, `refresh_token`, `code`, `access_token`, `id_token`, `password`
- 后缀匹配：`*_secret`, `*_token`, `*_password`
- 白名单：`client_id`（RFC 6749 允许 URL query）

**示例输出**：
```
🚨 检测到 1 个文件存在 OAuth credential 泄露风险:

   📁 /project/baidu_oauth.py
      L4: resp = httpx.get(
      敏感字段: code, client_secret
      风险: RFC 6749 §2.3.1 — confidential client 凭证不应在 URL query 中
      修复: 改用 data= 代替 params=，将凭证放入 POST body
```

### 3. 测试覆盖（5 个）

- `test_detects_sensitive_params_in_url_query` — 检测 params= 中的敏感字段
- `test_allows_client_id_in_url_query` — `client_id` 白名单
- `test_ignores_data_post_body` — `data=` 在 POST body 中不触发
- `test_main_exits_zero_when_clean` — 无违规时 exit 0
- `test_main_exits_one_when_violation` — 有违规时 exit 1

---

## 对 Agent 的影响

**写 OAuth adapter / token exchange 代码时**：

1. 运行 `vibe security-scan <project>` 检查是否有 credential 泄露
2. 如果检测到 `params={"client_secret": ...}`，改为 `data={"client_secret": ...}`
3. `client_id` 可以安全地在 URL query 中
4. 不要写 `password` / `code` / `refresh_token` / `access_token` 到 `params=`

**项目级补充**（参考妙藏 Gemkeep 的 R2.6）：
- 在 `.agents/rules/security.md` 中引用本规则
- 如果有 7 处以上已知例外，记录在规则文件中
- CI 集成 `vibe security-scan` 作为门禁

---

## 今日全部 6 项升级汇总

| # | 升级 | Commit | 说明 |
|---|------|--------|------|
| 1 | vibe next 自动 doctor | `a8bc97b` | 每次 `vibe next` 前自动跑 doctor |
| 2 | commit-msg hook 修复 | `a8bc97b` | 修正 hook 类型 + 测试绕过 |
| 3 | evidence digest 过期检测 | `d12d433` | amend 后自动检测并提示 |
| 4 | Skill 升级提案标准化 | `365025e` | 新增 `vibe propose-skill-upgrade` 命令 |
| 5 | R53 active inspection advisory | `e8a6b9e` | 门禁拦截后提醒 Agent 重读 diff |
| 6 | **OAuth credential-in-URL 安全扫描** | `5ec3b1b` | RFC 6749 §2.3.1 合规检测 |

---

## 当前完整标准操作

```bash
# 安全扫描（写 OAuth 代码时）
vibe security-scan <project>

# 初始化项目
vibe init <path>

# 查看下一步（自动跑 doctor + 检测未归档提案）
vibe next <project>

# 创建 skill 升级候选提案
vibe propose-skill-upgrade <project> "<标题>"

# 修改 spec（自动检测 evidence digest 过期）
vibe amend <project> <spec> "变更描述" --apply

# 提交代码（两步）
vibe commit <project>              # 看 diff，被拦时读 advisory
vibe commit --reviewed <project>   # verify + commit

# 写 retro（Review Agent 段新增 review quality 自检）
vibe retro <project> <spec>
```

---

## 测试状态

- 602 个测试全部通过
- VERSION: `5ec3b1b-oauth-credential-in-url-security-scan`
