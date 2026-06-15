# Changelog — v0.1.0

> 发布日期: 2026-06-14 | 基于分支: unknown

## 新增

- **ci-cd-detection**: `refresh_context.py` 尚未检测 CI/CD 配置文件（GitHub Actions、GitLab CI、CircleCI、
- **cli-sync**: vibe-cli 目前只封装了早期 6 个命令（init、spec、specs、plan、check、review），
- **context-freshness-reminder**: 当前工作流已经能刷新 `AGENTS.md`，但还不能在“上下文已经明显变旧”时主动提醒。
- **context-refresh-command**: 虽然 `refresh_context.py` 已经具备保守刷新 `AGENTS.md` 的能力，但用户仍需直接调
- **context-refresh-hardening**: `self_analyze` 已经提示当前项目的上下文准确性存在改进空间。现有
- **governance-hardening**
- **refresh-context-coverage**: `refresh_context.py` 当前的检测主要局限在项目根目录，对于多子项目/弱根配置的
- **retro-command**: 目前创建回顾仍需直接运行 `vibe-coding-skill/scripts/create_retro.py`，这让
- **self-analyze-context-filter**: `self-analyze-placeholder-filter` 修复了 `missing_rules` 和 `reviewer_missed` 的占位符过滤
- **self-analyze-placeholder-filter**: 当前 `self_analyze.py` 会把未填写完成的回顾模板占位文本也当成真实经验，
- **session-continuity**: 当前 `vibe next` 在所有 Spec 都 done 后只输出"创建或选择下一个工作项"，是冷启动。

## 修复

（无）

## 重构

- **suite-auxiliary-onboarding**: Vibe Coding 核心 Skill 的所有交互（init、spec、plan、prompt、review、retro、doctor 等）都在单 Skill

## 破坏性变更

（请手动列出破坏性变更）

## 依赖更新

（请手动列出依赖更新）

## 迁移指南

（如有破坏性变更，请补充迁移步骤）
