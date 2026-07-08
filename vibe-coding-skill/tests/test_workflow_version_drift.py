import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


class SkillVersionDriftTests(unittest.TestCase):
    """Cover 2026-07-09b feedback: doctor_project.py and upgrade.py
    must share one drift-detection function so both report the same
    verdict on the same VERSION file. Otherwise users see contradictory
    drift warnings from the two commands (one path says "no drift",
    the other says "drift").

    These tests exercise the shared `common.check_skill_version_drift`
    end-to-end via throwaway git repos, asserting:
      - silent (None) when VERSION was just bumped in HEAD
      - silent when working-tree VERSION begins with HEAD short hash
        (hybrid amend-safe shortcut)
      - warning when a feat commit landed without a follow-up bump
      - silent when no VERSION file exists
      - silent when no git history exists
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        subprocess.run(
            ["git", "init", "-q", "-b", "master", str(self.repo)],
            check=False, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(self.repo), "config", "user.email",
             "test@vibe.local"],
            check=False, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(self.repo), "config", "user.name",
             "Vibe Test"],
            check=False, capture_output=True,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _commit(self, msg: str, paths: list[str] | None = None) -> None:
        if paths:
            subprocess.run(
                ["git", "-C", str(self.repo), "add", "--", *paths],
                check=False, capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(self.repo), "commit", "-q", "-m", msg],
                check=False, capture_output=True,
            )
        else:
            subprocess.run(
                ["git", "-C", str(self.repo), "commit", "--allow-empty",
                 "-q", "-m", msg],
                check=False, capture_output=True,
            )

    def _write_version(self, content: str) -> None:
        (self.repo / "VERSION").write_text(content, encoding="utf-8")

    def test_silent_when_version_bumped_in_head(self) -> None:
        """When HEAD itself touched VERSION, no drift."""
        import common
        self._commit("feat: introduce VERSION")
        self._write_version("aaaaaaa-init\n")
        self._commit("chore: bump VERSION", paths=["VERSION"])
        self.assertIsNone(common.check_skill_version_drift(str(self.repo)))

    def test_silent_when_working_tree_aligned(self) -> None:
        """Hybrid amend-safe: working-tree VERSION starts with HEAD
        short hash even before commit lands, treat as no-drift."""
        import common
        self._commit("feat: hello")
        head = subprocess.check_output(
            ["git", "-C", str(self.repo), "rev-parse", "--short", "HEAD"],
            text=True,
        ).strip()
        # Write VERSION but DON'T commit yet — the amend-safe shortcut
        # should still recognize this as aligned.
        self._write_version(f"{head[:7]}-aligned-editing\n")
        self.assertIsNone(common.check_skill_version_drift(str(self.repo)))

    def test_warning_when_feat_landed_without_bump(self) -> None:
        """The actual failure mode: feat commit lands, VERSION is
        stale, doctor + upgrade must BOTH flag this (same verdict)."""
        import common
        self._commit("feat: real work")
        self._write_version("aaaaaaa-stale\n")
        self._commit("chore: initial VERSION", paths=["VERSION"])
        self._commit("feat: forgot to bump VERSION")
        warning = common.check_skill_version_drift(str(self.repo))
        self.assertIsNotNone(warning)
        self.assertIn("VERSION drift", warning)

    def test_silent_when_no_version_file(self) -> None:
        """No VERSION file → silent, never false-positive."""
        import common
        self._commit("feat: hello")
        # No VERSION file in repo.
        self.assertIsNone(common.check_skill_version_drift(str(self.repo)))

    def test_silent_when_no_git_history(self) -> None:
        """Untracked repo with VERSION but no commits → silent."""
        import common
        self._write_version("xxxxxxx-fake\n")
        self.assertIsNone(common.check_skill_version_drift(str(self.repo)))
