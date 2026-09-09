import pytest

from src.tenants import _slugify


@pytest.mark.parametrize(
    "name,expected",
    [
        ("TMDB Hit Classifier", "tmdb_hit_classifier"),
        ("Recruiter.AI", "recruiter_ai"),
        ("  Finio  ", "finio"),
        ("BD2026", "bd2026"),
    ],
)
def test_slugify_derives_expected_tenant_id(name, expected):
    assert _slugify(name) == expected


def test_slugify_raises_when_name_has_no_alphanumeric_characters():
    with pytest.raises(ValueError):
        _slugify("!!!")
