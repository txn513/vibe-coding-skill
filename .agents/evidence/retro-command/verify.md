# retro-command — verify

> 规格: retro-command | 规格摘要: 3b1248d4e3bc0202 | 上下文摘要: fd14a99a304d95f5 | 阶段: verify | 结果: passed
> 用途: standard
> Commit: not-a-git-repo | Snapshot: N/A | 工作区: unknown | Actor: codex | Role: builder
> 记录: 2026-06-13 20:31 UTC | 规格状态: in-progress | Exit: 0
> Command-Digests: d4601d2b4c2cb634

## 证据

验证 retro 命令入口与门禁


## 执行

```text
$ python3 -c 'import json, os, shutil, subprocess, sys, tempfile; root=os.getcwd(); vibe=[sys.executable, os.path.join(root, "vibe-cli", "vibe")]; help_out=subprocess.run(vibe+["--help"], cwd=root, capture_output=True, text=True, check=True).stdout; assert "retro" in help_out; reject=subprocess.run(vibe+["retro", "retro-command"], cwd=root, capture_output=True, text=True, check=False); assert reject.returncode == 0 and "只有状态为 done 的规格才能创建回顾" in reject.stdout; reuse=subprocess.run(vibe+["retro", "cli-sync"], cwd=root, capture_output=True, text=True, check=False); assert reuse.returncode == 0 and ("回顾文件已存在" in reuse.stdout or "回顾文件已创建" in reuse.stdout); tmp=tempfile.mkdtemp(); shutil.copy2(os.path.join(root, "AGENTS.md"), os.path.join(tmp, "AGENTS.md")); shutil.copytree(os.path.join(root, ".agents"), os.path.join(tmp, ".agents")); spec_path=os.path.join(tmp, ".agents", "specs", "example.md"); open(spec_path, "w", encoding="utf-8").write("# example\n\n> 状态: done | 创建: 2026-06-13 00:00 UTC | 更新: 2026-06-13 00:00 UTC\n> 类型: feature\n> 风险: low\n> 风险确认: confirmed\n> 负责人: test\n> 依赖: 无\n> 发布组: test\n\n## 意图 (Intent)\n\n**要解决什么问题？为谁解决？**\n\n用于测试 retro 命令。\n\n## 成功标准\n\n- 能创建回顾\n\n## 约束 (Constraints)\n\n### 技术约束\n- 无\n\n### 业务约束\n- 无\n\n### 明确不做什么 (Out of Scope)\n- 无\n\n## 验收标准 (Acceptance Criteria)\n\n### 正常路径\n1. 创建回顾\n\n### 边界情况\n- 无\n\n### 错误处理\n- 无\n\n## 非功能需求 (NFR)\n\n### 性能\n- 无\n\n### 安全\n- 无\n\n### 可访问性 / 兼容性\n- 无\n\n## 涉及范围\n\n- **新增文件**: 无\n- **修改文件**: 无\n- **不动文件**: 无\n\n## 验证方式\n\n- [ ] 创建回顾\n",); created=subprocess.run(vibe+["retro", "example"], cwd=tmp, capture_output=True, text=True, check=False); assert created.returncode == 0 and "回顾文件已创建" in created.stdout; assert os.path.exists(os.path.join(tmp, ".agents", "retros", "example.md")); print("retro command verification passed")'
retro command verification passed
```
