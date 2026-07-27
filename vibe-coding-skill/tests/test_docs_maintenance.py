"""Tests for R-D-87 docs maintenance features.

Covers:
- scripts/docs_init.py: skeleton generation + idempotency
- scripts/tidy.py: path validation, dry-run advise, --apply execution
- scripts/vibe.py: cheatsheet dispatch + filter, docs-init CLI dispatch
"""
from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

os.environ["VIBE_SKIP_COMMIT_MSG_HOOK"] = "1"

SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import docs_init  # noqa: E402
import tidy as tidy_mod  # noqa: E402
import vibe  # noqa: E402


class DocsInitTests(unittest.TestCase):
    """Cover scripts/docs_init.py: skeleton generation + idempotency."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name)
        (self.project / ".agents" / "specs").mkdir(parents=True)
        (self.project / ".agents" / "specs" / "auth.md").write_text(
            "# auth spec\n\n涉及模块:\n  - backend/auth.py\n  - frontend/login.tsx\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_dry_run_creates_no_files(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            docs_init.docs_init(str(self.project), dry_run=True)
        out = buf.getvalue()
        self.assertIn("计划创建", out, "dry-run should announce plan")
        self.assertFalse((self.project / "docs").exists(),
                         "dry-run must not create docs/")

    def test_apply_creates_full_skeleton(self) -> None:
        actions = docs_init.docs_init(str(self.project), dry_run=False)
        docs_dir = self.project / "docs"
        self.assertTrue(docs_dir.is_dir(), "docs/ should exist after --apply")
        for name in ("README.md", "overview.md", "tech-stack.md",
                     "architecture.md", "glossary.md"):
            self.assertTrue((docs_dir / name).is_file(),
                            f"docs/{name} missing")
        self.assertTrue((docs_dir / "adr" / "README.md").is_file(),
                        "docs/adr/README.md missing")

    def test_modules_detected_from_specs(self) -> None:
        actions = docs_init.docs_init(str(self.project), dry_run=False)
        module_docs = [a for a in actions if "/modules/" in a["path"]]
        names = {os.path.basename(a["path"]) for a in module_docs}
        # regex extracts `backend/auth.py` -> module name is `auth.py` -> file is auth.py.md
        self.assertIn("auth.py.md", names,
                      f"auth module should be detected, got: {names}")

    def test_idempotent_second_run_is_noop(self) -> None:
        docs_init.docs_init(str(self.project), dry_run=False)
        buf = io.StringIO()
        with redirect_stdout(buf):
            actions = docs_init.docs_init(str(self.project), dry_run=False)
        self.assertEqual(actions, [], "second run must be no-op")
        out = buf.getvalue()
        self.assertIn("already initialized", out)

    def test_generated_files_have_frontmatter(self) -> None:
        docs_init.docs_init(str(self.project), dry_run=False)
        readme = (self.project / "docs" / "README.md").read_text(encoding="utf-8")
        self.assertIn("last_updated:", readme)
        self.assertIn("status:", readme)

    def test_empty_project_with_no_specs_returns_baseline(self) -> None:
        import shutil
        shutil.rmtree(self.project / ".agents" / "specs")
        actions = docs_init.docs_init(str(self.project), dry_run=False)
        self.assertGreater(len(actions), 0)
        self.assertTrue((self.project / "docs" / "README.md").is_file())


class TidyTests(unittest.TestCase):
    """Cover scripts/tidy.py: path validation + dry-run advise + apply."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_main_rejects_missing_path_with_exit_2(self) -> None:
        missing = self.project / "nope"
        buf_out, buf_err = io.StringIO(), io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            with self.assertRaises(SystemExit) as cm:
                tidy_mod.main()
                # override argv inline
        # argparse consumes sys.argv; we test via direct invocation
        old_argv = sys.argv
        try:
            sys.argv = ["tidy.py", str(missing)]
            buf_out2, buf_err2 = io.StringIO(), io.StringIO()
            with redirect_stdout(buf_out2), redirect_stderr(buf_err2):
                with self.assertRaises(SystemExit) as cm:
                    tidy_mod.main()
            self.assertEqual(cm.exception.code, 2)
            self.assertIn("Error: project_root does not exist", buf_err2.getvalue())
        finally:
            sys.argv = old_argv

    def test_docs_init_resolves_missing_docs_advise(self) -> None:
        # Before docs-init: tidy advises "docs/ missing"
        pre = tidy_mod.tidy(str(self.project), dry_run=True)
        pre_docs_advise = [a for a in pre if a.get("src") == "docs/"]
        self.assertEqual(len(pre_docs_advise), 1, "expected 1 docs/ missing advise")

        # After docs-init: the "docs/ missing" advise is gone
        docs_init.docs_init(str(self.project), dry_run=False)
        post = tidy_mod.tidy(str(self.project), dry_run=True)
        post_missing = [a for a in post if a.get("src") == "docs/"
                        and "missing" in a.get("reason", "")]
        self.assertEqual(post_missing, [],
                         f"docs/ missing advise should be gone, got: {post_missing}")

    def test_freshly_initialized_docs_not_flagged_as_orphan(self) -> None:
        # Regression test: docs-init creates docs/README.md with [text](file.md)
        # style links. tidy's orphan regex must capture the URL side, not the
        # link text side, otherwise every freshly-created file gets flagged.
        docs_init.docs_init(str(self.project), dry_run=False)
        actions = tidy_mod.tidy(str(self.project), dry_run=True)
        orphans = [a for a in actions
                   if a.get("src", "").startswith("docs/")
                   and "orphan" in a.get("reason", "")]
        # adr/README.md is intentionally not linked from index (directory marker)
        linked_orphans = [o for o in orphans if o["src"] != "docs/adr/README.md"]
        self.assertEqual(linked_orphans, [],
                         f"linked docs wrongly flagged as orphan: {linked_orphans}")

    def test_missing_docs_emits_advise(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            actions = tidy_mod.tidy(str(self.project), dry_run=True)
        advise = [a for a in actions if a["action"] == "advise"]
        advise_reasons = [a["reason"] for a in advise]
        self.assertTrue(any("docs/" in r for r in advise_reasons),
                        f"expected docs/ advise, got: {advise_reasons}")

    def test_advise_actions_not_executed_on_apply(self) -> None:
        # missing docs/ should not be auto-created by --apply (it's advise only)
        tidy_mod.tidy(str(self.project), dry_run=False)
        self.assertFalse((self.project / "docs").exists(),
                         "tidy --apply must not auto-create docs/ (advisory)")


class CheatsheetDispatchTests(unittest.TestCase):
    """Cover scripts/vibe.py cheatsheet + docs-init dispatch."""

    def test_cheatsheet_full_output(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            vibe._print_cheatsheet()
        out = buf.getvalue()
        self.assertIn("VIBE CHEATSHEET", out)
        self.assertIn("Bootstrap", out)
        self.assertIn("Housekeeping", out)
        self.assertIn("vibe docs-init", out)
        self.assertIn("R-D-87", out)

    def test_cheatsheet_filter_narrows_output(self) -> None:
        full = io.StringIO()
        with redirect_stdout(full):
            vibe._print_cheatsheet()
        full_lines = full.getvalue().count("\n")

        filtered = io.StringIO()
        with redirect_stdout(filtered):
            vibe._print_cheatsheet(filter_kw="docs")
        filtered_out = filtered.getvalue()
        filtered_lines = filtered_out.count("\n")

        self.assertLess(filtered_lines, full_lines)
        self.assertIn("filter: docs", filtered_out)
        # the docs-init line must be present
        self.assertIn("vibe docs-init", filtered_out)
        # unrelated commands must be filtered out
        self.assertNotIn("vibe install-precommit-hook", filtered_out)

    def test_cheatsheet_filter_no_match_drops_all(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            vibe._print_cheatsheet(filter_kw="__nope_definitely_no_match__")
        # when nothing matches, all groups are empty -> just the banner + tip
        out = buf.getvalue()
        self.assertIn("VIBE CHEATSHEET", out)
        self.assertNotIn("Bootstrap", out)


class VibeDocsInitCLITests(unittest.TestCase):
    """Cover scripts/vibe.py docs-init subcommand end-to-end via subprocess."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name)
        (self.project / ".agents" / "specs").mkdir(parents=True)
        (self.project / ".agents" / "specs" / "demo.md").write_text(
            "# demo\n\n涉及 backend/x.py\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run_vibe(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "vibe.py"), *args],
            cwd=str(SKILL_DIR),
            capture_output=True,
            text=True,
            env={**os.environ, "VIBE_SKIP_COMMIT_MSG_HOOK": "1"},
        )

    def test_docs_init_dry_run_subprocess(self) -> None:
        result = self._run_vibe("docs-init", str(self.project), "--dry-run")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertFalse((self.project / "docs").exists())
        self.assertIn("计划创建", result.stdout)

    def test_docs_init_apply_subprocess(self) -> None:
        result = self._run_vibe("docs-init", str(self.project), "--apply")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertTrue((self.project / "docs" / "README.md").is_file())


if __name__ == "__main__":
    unittest.main()
