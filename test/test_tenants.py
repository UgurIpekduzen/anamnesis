"""Tests for deriving a tenant id from a project name."""

import pytest

from src.projects.tenants import _slugify


@pytest.mark.parametrize(
    "name,expected",
    [
        ("My Project", "my_project"),
        ("Demo.Shop", "demo_shop"),
        ("  Blog  ", "blog"),
        ("APP2026", "app2026"),
    ],
)
def test_slugify_derives_expected_tenant_id(name, expected):
    """_slugify lowercases a project name, replaces separators with underscores, and trims surrounding whitespace."""
    assert _slugify(name) == expected


def test_slugify_raises_when_name_has_no_alphanumeric_characters():
    """A name with no alphanumeric characters at all raises a ValueError."""
    with pytest.raises(ValueError):
        _slugify("!!!")
