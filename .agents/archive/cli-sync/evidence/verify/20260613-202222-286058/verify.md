# cli-sync — verify

> 规格: cli-sync | 规格摘要: 2f7cf6becfaad4d2 | 上下文摘要: fd14a99a304d95f5 | 阶段: verify | 结果: failed
> 用途: standard
> Commit: not-a-git-repo | Snapshot: N/A | 工作区: unknown | Actor: codex | Role: builder
> 记录: 2026-06-13 20:21 UTC | 规格状态: in-progress | Exit: 1
> Command-Digests: ae9491dd6c921712

## 证据

验证 cli-sync CLI 转发行为


## 执行

```text
$ python3 -c 'import subprocess, tempfile, os; root=os.getcwd(); vibe=["python3", "vibe-cli/vibe"]; help_out=subprocess.run(vibe+["--help"], cwd=root, capture_output=True, text=True, check=True).stdout; assert "review-decision" in help_out and "policy-scan" in help_out; next_out=subprocess.run(vibe+["next"], cwd=root, capture_output=True, text=True, check=True).stdout; assert "cli-sync" in next_out and "进入实施并按计划执行" in next_out; status_out=subprocess.run(vibe+["status"], cwd=root, capture_output=True, text=True, check=True).stdout; assert "spec-ready" in status_out or "in-progress" in status_out; doctor_out=subprocess.run(vibe+["doctor"], cwd=root, capture_output=True, text=True, check=True).stdout; assert "No workflow integrity issues found." in doctor_out; tmp=tempfile.mkdtemp(); empty_out=subprocess.run(vibe+["next"], cwd=tmp, capture_output=True, text=True, check=True).stdout; assert "接入已有项目或初始化新项目" in empty_out; print("cli-sync verification passed")'
Traceback (most recent call last):
  File "<string>", line 1, in <module>
    import subprocess, tempfile, os; root=os.getcwd(); vibe=["python3", "vibe-cli/vibe"]; help_out=subprocess.run(vibe+["--help"], cwd=root, capture_output=True, text=True, check=True).stdout; assert "review-decision" in help_out and "policy-scan" in help_out; next_out=subprocess.run(vibe+["next"], cwd=root, capture_output=True, text=True, check=True).stdout; assert "cli-sync" in next_out and "进入实施并按计划执行" in next_out; status_out=subprocess.run(vibe+["status"], cwd=root, capture_output=True, text=True, check=True).stdout; assert "spec-ready" in status_out or "in-progress" in status_out; doctor_out=subprocess.run(vibe+["doctor"], cwd=root, capture_output=True, text=True, check=True).stdout; assert "No workflow integrity issues found." in doctor_out; tmp=tempfile.mkdtemp(); empty_out=subprocess.run(vibe+["next"], cwd=tmp, capture_output=True, text=True, check=True).stdout; assert "接入已有项目或初始化新项目" in empty_out; print("cli-sync verification passed")
                                                                                                                                                                                                                                                                                                                                                                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError
```
