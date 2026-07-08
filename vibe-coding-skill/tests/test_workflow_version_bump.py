import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


class VersionBumpTests(unittest.TestCase):
    """Cover 2026-07-09 (Lance retro on social-bookmarking-tool):

    Maintainers historically hand-typed `chore(skill): bump VERSION to
    <hash>-<slug>` commits and repeatedly put the **previous** feat
    commit's hash into the VERSION file content. The new `vibe
    version-bump` command closes that loop by computing the hash and
    slug from git itself, eliminating the human-error window.
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

    def _commit(self, msg: str) -> None:
        subprocess.run(
            ["git", "-C", str(self.repo), "commit", "--allow-empty",
             "-q", "-m", msg],
            check=False, capture_output=True,
        )

    def _run_git(self, *args: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(self.repo), *args],
            text=True,
        ).strip()

    def test_slugify_lowercases_and_dashes(self) -> None:
        import version_bump
        self.assertEqual(
            version_bump._slugify_subject("Fix Login Bug!"),
            "fix-login-bug",
        )

    def test_slugify_collapses_runs_and_trims(self) -> None:
        import version_bump
        self.assertEqual(
            version_bump._slugify_subject("  --foo__BAR..baz--  "),
            "foo-bar-baz",
        )

    def test_slugify_handles_empty_subject(self) -> None:
        import version_bump
        self.assertEqual(version_bump._slugify_subject(""), "unnamed")
        self.assertEqual(version_bump._slugify_subject("   "), "unnamed")
        self.assertEqual(version_bump._slugify_subject("---"), "unnamed")

    def test_slugify_bounds_length(self) -> None:
        import version_bump
        long_subject = "x" * 200
        slug = version_bump._slugify_subject(long_subject, max_len=10)
        self.assertEqual(len(slug), 10)
        self.assertTrue(slug.startswith("x"))

    def test_feat_subject_uses_head_when_not_bump(self) -> None:
        """If HEAD is a feat commit, slug is sourced from it directly."""
        import version_bump
        self._commit("feat: cover edge case")
        pre_hash, slug = version_bump._feat_subject(str(self.repo))
        head = self._run_git("rev-parse", "--short", "HEAD")
        self.assertEqual(pre_hash, head)
        self.assertEqual(slug, "feat-cover-edge-case")

    def test_feat_subject_skips_previous_bump(self) -> None:
        """If HEAD is a chore bump commit, slug is sourced from the
        commit before it (the actual feat commit)."""
        import version_bump
        self._commit("feat: real feature")
        self._commit("chore(skill): bump VERSION")
        pre_hash, slug = version_bump._feat_subject(str(self.repo))
        head_after_bump = self._run_git("rev-parse", "--short", "HEAD")
        self.assertEqual(pre_hash, head_after_bump)
        self.assertEqual(slug, "feat-real-feature")

    def test_feat_subject_walks_back_multiple_bumps(self) -> None:
        """If HEAD has multiple consecutive bump commits (e.g. from
        repeated bump calls before tree was clean), skip them all."""
        import version_bump
        self._commit("feat: deep feature")
        self._commit("chore(skill): bump VERSION")
        self._commit("chore(skill): bump VERSION")
        self._commit("chore(skill): bump VERSION")
        _, slug = version_bump._feat_subject(str(self.repo))
        self.assertEqual(slug, "feat-deep-feature")

    def test_bump_recovers_from_drift_state(self) -> None:
        """End-to-end: stale VERSION → bump → drift cleared.

        Verified by `_check_skill_version_drift()`'s invariant: the
        last commit that touched VERSION must equal HEAD after bump.
        """
        self._commit("feat: cover edge case")
        version_path = self.repo / "VERSION"
        version_path.write_text("aaaaaaa-stale-drift\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(self.repo), "add", "VERSION"],
            check=False, capture_output=True,
        )
        self._commit("chore: seeded stale VERSION")

        import version_bump
        original_dir = version_bump._SKILL_DIR
        version_bump._SKILL_DIR = str(self.repo)
        try:
            rc = version_bump.bump()
        finally:
            version_bump._SKILL_DIR = original_dir
        self.assertEqual(rc, 0, "bump must succeed on drift state")

        last_version_touch = subprocess.check_output(
            ["git", "-C", str(self.repo), "log", "-1", "--format=%H",
             "--", "VERSION"],
            text=True,
        ).strip()
        head = self._run_git("rev-parse", "HEAD")
        self.assertEqual(
            last_version_touch, head,
            "bump must make HEAD the last commit that touched VERSION",
        )

    def test_bump_idempotent_after_a_bump(self) -> None:
        """If HEAD is already a bump commit and tree is clean, a
        second bump call must be a no-op (no new commit)."""
        import version_bump
        self._commit("feat: hello world")
        version_path = self.repo / "VERSION"
        version_path.write_text("placeholder\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(self.repo), "add", "VERSION"],
            check=False, capture_output=True,
        )
        original_dir = version_bump._SKILL_DIR
        version_bump._SKILL_DIR = str(self.repo)
        try:
            rc1 = version_bump.bump()
            after_first = self._run_git("rev-parse", "HEAD")
            rc2 = version_bump.bump()
            after_second = self._run_git("rev-parse", "HEAD")
        finally:
            version_bump._SKILL_DIR = original_dir
        self.assertEqual(rc1, 0)
        self.assertEqual(rc2, 0)
        self.assertEqual(
            after_first, after_second,
            "second bump must be a no-op when HEAD is already a bump commit",
        )
