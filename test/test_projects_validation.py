import pytest

from src.projects.validation import validate_github_repo, validate_project_key


@pytest.mark.parametrize("key", ["APPCE", "APP2026", "AB", "A_1", "X" * 50])
def test_a_plain_project_key_is_accepted(key):
    validate_project_key(key)


@pytest.mark.parametrize(
    "key",
    [
        "",
        "a",
        "appce",  # lowercase
        "A",  # a single character
        "1ABC",  # starts with a digit
        "AB CD",
        "AB-CD",
        'X" OR project != "',  # would change the meaning of the query it is put into
        "X\nY",
        "X" * 51,
        None,
        123,
    ],
)
def test_anything_that_is_not_a_plain_project_key_is_rejected(key):
    with pytest.raises(ValueError):
        validate_project_key(key)


@pytest.mark.parametrize("repo", ["UgurIpekduzen/anamnesis", "a/b", "some-org/some.repo_name-2", "x" * 39 + "/y"])
def test_a_plain_owner_and_name_is_accepted(repo):
    validate_github_repo(repo)


@pytest.mark.parametrize(
    "repo",
    [
        "",
        "anamnesis",  # no owner
        "/anamnesis",
        "owner/",
        "owner/name/extra",
        "-owner/name",  # an owner can't start with a hyphen
        "owner name/repo",
        "https://github.com/owner/name",  # a URL, not owner/name
        "owner/name?x=1",
        "owner/../name",
        "x" * 40 + "/y",  # owner longer than GitHub allows
        None,
        123,
    ],
)
def test_anything_that_is_not_a_plain_owner_and_name_is_rejected(repo):
    with pytest.raises(ValueError):
        validate_github_repo(repo)
