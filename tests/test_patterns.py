"""Tests for the shared glob matcher used by branches, paths, needs_nothing."""

import pytest

from tests.conftest import git_cicd

match = git_cicd.match


@pytest.mark.parametrize("pattern,path,expected", [
    # literal
    ("main", "main", True),
    ("main", "mainline", False),
    ("a.b", "axb", False),
    # *
    ("*.md", "README.md", True),
    ("*.md", "docs/README.md", False),
    ("src/*.py", "src/a.py", True),
    ("src/*.py", "src/sub/a.py", False),
    ("plan/*", "plan/x", True),
    ("plan/*", "plan/x/y", False),
    ("*", "anything", True),
    ("*", "a/b", False),
    # **
    ("**", "a/b/c", True),
    ("**", "main", True),
    ("plan/**", "plan/mdci-dev-6692", True),
    ("plan/**", "plan/a/b", True),
    ("plan/**", "plan", False),
    ("plan/**", "planx/a", False),
    ("medici/**", "medici/x.py", True),
    ("medici/**", "tests/x.py", False),
    ("**/*.md", "docs/a/b.md", True),
    ("**/*.md", "README.md", True),
    ("docs/**/x", "docs/x", True),
    ("docs/**/x", "docs/a/b/x", True),
    ("a**b", "a/x/b", True),
    # ?
    ("v?", "v1", True),
    ("v?", "v12", False),
    ("a?b", "a/b", False),
    ("a?b", "a-b", True),
    # other regex characters are literal
    ("[ab]", "a", False),
    ("[ab]", "[ab]", True),
    ("a+b", "a+b", True),
])
def test_match(pattern, path, expected):
    assert match(pattern, path) is expected


def test_match_any():
    assert git_cicd.match_any(["x", "*.md"], "a.md")
    assert not git_cicd.match_any([], "a.md")
