# cli-sync — verify

> 规格: cli-sync | 规格摘要: 2f7cf6becfaad4d2 | 上下文摘要: fd14a99a304d95f5 | 阶段: verify | 结果: passed
> 用途: standard
> Commit: not-a-git-repo | Snapshot: N/A | 工作区: unknown | Actor: codex | Role: builder
> 记录: 2026-06-13 20:22 UTC | 规格状态: in-progress | Exit: 0
> Command-Digests: 80f0ae935a81195e

## 证据

验证 cli-sync CLI 转发行为


## 执行

```text
$ python3 -c 'import subprocess, tempfile, os; root=os.getcwd(); vibe=["python3", os.path.join(root, "vibe-cli", "vibe")]; help_out=subprocess.run(vibe+["--help"], cwd=root, capture_output=True, text=True, check=True).stdout; assert "review-decision" in help_out and "policy-scan" in help_out; next_out=subprocess.run(vibe+["next"], cwd=root, capture_output=True, text=True, check=True).stdout; assert "完成验证并记录证据" in next_out and "cli-sync" in next_out; status_out=subprocess.run(vibe+["status"], cwd=root, capture_output=True, text=True, check=True).stdout; assert "功能规格" in status_out and "cli-sync" in status_out; doctor_out=subprocess.run(vibe+["doctor"], cwd=root, capture_output=True, text=True, check=True).stdout; assert "No workflow integrity issues found." in doctor_out; tmp=tempfile.mkdtemp(); empty_out=subprocess.run(vibe+["next"], cwd=tmp, capture_output=True, text=True, check=True).stdout; assert "接入已有项目或初始化新项目" in empty_out; print("cli-sync verification passed")'
cli-sync verification passed
```
