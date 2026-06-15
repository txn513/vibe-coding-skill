# context-refresh-command — verify

> 规格: context-refresh-command | 规格摘要: 867fc09de6308089 | 上下文摘要: 0ac7d0d38156b485 | 阶段: verify | 结果: passed
> 用途: standard
> Commit: not-a-git-repo | Snapshot: N/A | 工作区: unknown | Actor: codex | Role: builder
> 记录: 2026-06-13 20:48 UTC | 规格状态: draft | Exit: 0
> Command-Digests: 5b718b3c1d8e4ca2

## 证据

验证 context-refresh 命令入口


## 执行

```text
$ python3 -c 'import os, subprocess, sys; root=os.getcwd(); vibe=[sys.executable, os.path.join(root, "vibe-cli", "vibe")]; help_out=subprocess.run(vibe+["--help"], cwd=root, capture_output=True, text=True, check=True).stdout; assert "context-refresh" in help_out; run_out=subprocess.run(vibe+["context-refresh"], cwd=root, capture_output=True, text=True, check=True).stdout; assert "AGENTS.md 已刷新" in run_out or "上下文已是最新" in run_out; print("context-refresh command verification passed")'
context-refresh command verification passed
```
