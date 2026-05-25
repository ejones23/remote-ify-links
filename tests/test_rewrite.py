"""Unit tests for the rewrite engine.

Each test calls `rewrite()` directly with synthetic owner/repo/ref/repo_root
values so the tests don't depend on the local git environment. The
`fixtures/` directory holds whole-document input/expected pairs lifted from
real PR drafts — those are the regression cases the user cares about most.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "remote-ify-links.py"

# The script's filename has a hyphen, so import it via spec.
_spec = importlib.util.spec_from_file_location("remote_ify_links", SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["remote_ify_links"] = _mod
_spec.loader.exec_module(_mod)
rewrite = _mod.rewrite


# A synthetic repo root that always exists on POSIX systems and never overlaps
# with a real checkout. Tests use paths under this prefix.
FAKE_REPO_ROOT = Path("/tmp/fake-repo-root-for-tests")
OWNER = "acme"
REPO = "widget"
REF = "main"


def _r(text: str, repo_root: Path = FAKE_REPO_ROOT) -> str:
    return rewrite(text, OWNER, REPO, REF, repo_root)


class CitationFormatTests(unittest.TestCase):
    """The new `@/abs/path[:N[-M]]` citation form."""

    def test_range_citation_uses_basename_label_when_unique(self):
        text = "see `@/tmp/fake-repo-root-for-tests/src/foo.py:5-10`."
        out = _r(text)
        self.assertEqual(
            out,
            "see [foo.py:5-10](https://github.com/acme/widget/blob/main/src/foo.py#L5-L10).",
        )

    def test_single_line_citation(self):
        text = "see `@/tmp/fake-repo-root-for-tests/src/foo.py:42`."
        out = _r(text)
        self.assertEqual(
            out,
            "see [foo.py:42](https://github.com/acme/widget/blob/main/src/foo.py#L42).",
        )

    def test_whole_file_citation(self):
        text = "see `@/tmp/fake-repo-root-for-tests/src/foo.py`."
        out = _r(text)
        self.assertEqual(
            out,
            "see [foo.py](https://github.com/acme/widget/blob/main/src/foo.py).",
        )

    def test_basename_collision_falls_back_to_relpath(self):
        """When two distinct paths share a basename, the label uses the relpath."""
        text = (
            "first `@/tmp/fake-repo-root-for-tests/a/foo.py:1` "
            "second `@/tmp/fake-repo-root-for-tests/b/foo.py:2`"
        )
        out = _r(text)
        self.assertIn(
            "[a/foo.py:1](https://github.com/acme/widget/blob/main/a/foo.py#L1)",
            out,
        )
        self.assertIn(
            "[b/foo.py:2](https://github.com/acme/widget/blob/main/b/foo.py#L2)",
            out,
        )

    def test_same_path_multiple_ranges_keeps_basename(self):
        """The same file referenced at different line ranges is still unambiguous."""
        text = (
            "a `@/tmp/fake-repo-root-for-tests/src/foo.py:5-10` and "
            "b `@/tmp/fake-repo-root-for-tests/src/foo.py:20-30`"
        )
        out = _r(text)
        self.assertIn("[foo.py:5-10](", out)
        self.assertIn("[foo.py:20-30](", out)

    def test_path_outside_repo_left_unchanged(self):
        text = "ext `@/etc/passwd:1`."
        out = _r(text)
        self.assertEqual(out, text)

    def test_unbacktick_citation_is_left_alone(self):
        """Bare @/path... in prose must not be rewritten."""
        text = "talk to me about @/tmp/fake-repo-root-for-tests/src/foo.py:1 sometime"
        out = _r(text)
        self.assertEqual(out, text)

    def test_single_line_endpoints_collapse_in_url(self):
        """`@/.../foo.py:5-5` should produce `#L5`, not `#L5-L5`."""
        text = "x `@/tmp/fake-repo-root-for-tests/src/foo.py:5-5`"
        out = _r(text)
        self.assertIn("#L5)", out)
        self.assertNotIn("#L5-L5", out)


class CciLinkBackCompatTests(unittest.TestCase):
    """The pre-existing cci://file:// link form must keep working."""

    def test_cci_range_link(self):
        text = "[foo](cci:1://file:///tmp/fake-repo-root-for-tests/src/foo.py:7:0-13:1)"
        out = _r(text)
        self.assertEqual(
            out,
            "[foo](https://github.com/acme/widget/blob/main/src/foo.py#L7-L13)",
        )

    def test_cci_whole_file_link(self):
        text = "[foo](cci:7://file:///tmp/fake-repo-root-for-tests/src/foo.py:0:0-0:0)"
        out = _r(text)
        self.assertEqual(
            out,
            "[foo](https://github.com/acme/widget/blob/main/src/foo.py)",
        )

    def test_cci_outside_repo_left_unchanged(self):
        text = "[foo](cci:1://file:///etc/passwd:1:0-2:0)"
        out = _r(text)
        self.assertEqual(out, text)


class FixtureRoundTripTests(unittest.TestCase):
    """Compare whole-document input/expected fixtures byte-for-byte.

    Add new pairs as `tests/fixtures/<name>.input.md` and
    `tests/fixtures/<name>.expected.md`. These are the canonical PR-draft
    regression cases.
    """

    fixtures_dir = REPO_ROOT / "tests" / "fixtures"

    def test_all_fixtures(self):
        if not self.fixtures_dir.exists():
            self.skipTest("no fixtures directory")
        inputs = sorted(self.fixtures_dir.glob("*.input.md"))
        self.assertGreater(len(inputs), 0, "no fixture inputs found")
        for input_path in inputs:
            name = input_path.name.removesuffix(".input.md")
            expected_path = self.fixtures_dir / f"{name}.expected.md"
            with self.subTest(fixture=name):
                self.assertTrue(
                    expected_path.exists(),
                    f"missing expected file for fixture {name!r}",
                )
                got = rewrite(
                    input_path.read_text(),
                    OWNER,
                    REPO,
                    REF,
                    FAKE_REPO_ROOT,
                )
                want = expected_path.read_text()
                self.assertEqual(got, want, f"fixture {name!r} mismatch")


if __name__ == "__main__":
    unittest.main()
