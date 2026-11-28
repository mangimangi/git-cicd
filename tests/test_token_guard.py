"""The suite never reads a real token from the environment."""

import os

from tests.conftest import TOKEN_NAMES


def test_no_token_in_the_environment():
    """ci/test.sh sets every name to a sentinel before running pytest; the
    autouse fixture in tests/conftest.py removes them, so this fails when
    that guard is removed."""
    assert TOKEN_NAMES == ("CICD_WRITE_TOKEN", "CICD_READ_TOKEN",
                           "VENDOR_PAT", "GH_TOKEN", "GITHUB_TOKEN")
    assert [k for k in TOKEN_NAMES if k in os.environ] == []
