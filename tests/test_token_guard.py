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


def test_no_platform_variable_in_the_environment():
    """The autouse fixture also removes every GITHUB_* and CICD_* variable a
    test did not set itself, so a test sees the same environment locally and
    in Actions."""
    assert [k for k in os.environ
            if k.startswith(("GITHUB_", "CICD_"))] == []
