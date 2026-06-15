# self-analyze-context-filter — verify

> 规格: self-analyze-context-filter | 规格摘要: 44233380ce0d7a30 | 上下文摘要: 356a554c668bdced | 阶段: verify | 结果: passed
> 用途: standard
> Commit: not-a-git-repo | Snapshot: N/A | 工作区: unknown | Actor: 未记录 | Role: 未记录
> 记录: 2026-06-13 21:59 UTC | 规格状态: in-progress | Exit: 0
> Command-Digests: 3c4625968e2fa04b

## 证据

self_analyze output clean


## 执行

```text
$ python3 -c 'import sys; sys.path.insert(0,'"'"'vibe-coding-skill/scripts'"'"'); import self_analyze; r=self_analyze.analyze('"'"'.'"'"'); assert not r.get('"'"'context_issues'"'"',{}).get('"'"'AGENTS.md 不准确'"'"',0), '"'"'still has noise'"'"''

```
