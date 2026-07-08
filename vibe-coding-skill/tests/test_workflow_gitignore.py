"""Verify Skill repo .gitignore permits tracking .agents/workflow.json."""
import subprocess
import unittest
from pathlib import Path
SKILL_DIR = Path(__file__).resolve().parents[1]

class SkillGitignoreWorkflowTests(unittest.TestCase):
    def test_workflow_json_is_not_ignored(self) -> None:
        result = subprocess.run(
            ["git", "check-ignore", str(SKILL_DIR / ".agents" / "workflow.json")],
            cwd=str(SKILL_DIR), capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0, ".agents/workflow.json is git-ignored")
    def test_init_project_artefacts_are_ignored(self) -> None:
        for relpath in (".agents/rules/api.md", ".agents/specs/example.md",
                        ".agents/plans/example.md", ".agents/reviews/example.md", "AGENTS.md"):
            with self.subTest(relpath=relpath):
                result = subprocess.run(["git", "check-ignore", relpath], cwd=str(SKILL_DIR), capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, relpath + " should be git-ignored")
