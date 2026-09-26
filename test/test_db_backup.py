from datetime import datetime, timedelta, timezone

import pytest

from src import db_backup


def test_values_survive_a_round_trip_through_json():
    original = {
        "name": "x",
        "count": 3,
        "ratio": 0.5,
        "flag": True,
        "nothing": None,
        "when": datetime(2026, 9, 26, 3, 11, 49, 123456, tzinfo=timezone.utc),
        "token": b"\x00\xffbinary",
        "nested": {"list": [1, "two", {"at": datetime(2026, 1, 1, tzinfo=timezone.utc)}]},
    }

    import json

    restored = db_backup._decode(json.loads(json.dumps(db_backup._encode(original))))

    assert restored == original


def test_a_time_with_another_offset_comes_back_as_the_same_moment():
    local = datetime(2026, 9, 26, 6, 0, tzinfo=timezone(timedelta(hours=3)))

    restored = db_backup._decode(db_backup._encode(local))

    assert restored == local


def test_a_value_it_cannot_store_stops_the_backup():
    with pytest.raises(TypeError):
        db_backup._encode({"ref": object()})


def test_load_refuses_to_run_against_the_real_database(monkeypatch, tmp_path):
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    dump_file = tmp_path / "dump.json"
    dump_file.write_text('{"format": 1, "documents": []}')

    with pytest.raises(SystemExit, match="FIRESTORE_EMULATOR_HOST"):
        db_backup.load(str(dump_file))
