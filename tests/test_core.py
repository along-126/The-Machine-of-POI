"""Core tests run offline. No camera, network or source face photos required."""
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2
import numpy as np
import pytest

from camera_sources import validate_stream_url
from classifications import CATEGORIES, LABELS, category_for
from database import Database
from hud import render
from metadata import clock_text, coordinates_text
from tracking import FaceTracker, intersection_over_union


def test_all_seven_categories_and_captions():
    assert len(CATEGORIES) == 7
    assert len(LABELS) == 14
    assert category_for("ASSET CATALYST").key == "BLUE"
    assert "ASSET" not in LABELS
    assert "CATALYST" not in LABELS
    assert category_for("ADMIN").key == "YELLOW"
    assert category_for("IRRELEVANT THREAT").key == "IRRELEVANT_THREAT"
    assert category_for("ROOT").key == "ANALOG"
    assert category_for("RELEVANT-OTHER").key == "RELEVANT"


def test_database_roundtrip():
    with tempfile.TemporaryDirectory() as folder:
        db = Database(Path(folder)/"people.db")
        a = np.arange(128, dtype=np.float32)
        pid = db.add_person("测试用户", "ADMIN", a)
        assert db.get_people()[0][1:4] == ("测试用户", "ADMIN", 1)
        assert db.get_embeddings()[0][2] == "ADMIN"
        db.add_sample(pid, a)
        assert len(db.get_embeddings()) == 2
        db.update_label(pid, "RELEVANT-TWO")
        assert db.get_people()[0][2] == "RELEVANT-TWO"
        db.remove(pid)
        assert db.get_people() == []
        db.close()


def test_reject_same_photo_two_identities():
    with tempfile.TemporaryDirectory() as folder:
        db = Database(Path(folder)/"people.db")
        v = np.arange(128, dtype=np.float32)
        db.add_person("张甲", "ADMIN", v)
        with pytest.raises(ValueError, match="不能分配第二个身份"):
            db.add_person("张乙", "THREAT", v.copy())
        assert len(db.get_people()) == 1
        db.close()


def test_upgrade_old_database_keeps_samples_and_backup():
    with tempfile.TemporaryDirectory() as folder:
        db_file = Path(folder)/"machine.db"
        # Commit the fixture transaction, then release its Windows file handle.
        with closing(sqlite3.connect(db_file)) as con, con:
            con.execute("""CREATE TABLE people (
              id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
              label TEXT NOT NULL CHECK(label IN ('IRRELEVANT','THREAT','CONTINGENCY','INDIGO'))
            )""")
            con.execute("""CREATE TABLE face_samples (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
              vector BLOB NOT NULL)""")
            con.execute("INSERT INTO people(name,label) VALUES('ADMIN','CONTINGENCY')")
            con.execute("INSERT INTO people(name,label) VALUES('Blue','INDIGO')")
            con.execute("INSERT INTO face_samples(person_id,vector) VALUES(?,?)",
                        (1, np.ones(128,dtype=np.float32).tobytes()))
            con.execute("INSERT INTO face_samples(person_id,vector) VALUES(?,?)",
                        (2, np.ones(128,dtype=np.float32).tobytes()))
        db = Database(db_file)
        assert [x[2] for x in db.get_people()] == ["ADMIN", "ASSET CATALYST"]
        assert [x[3] for x in db.get_people()] == [1, 1]
        assert db.connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        db.add_person("新人物", "ROOT", np.arange(128,dtype=np.float32))
        db.remove(1)
        assert db.connection.execute("SELECT COUNT(*) FROM face_samples WHERE person_id=1").fetchone()[0] == 0
        assert len(list(Path(folder).glob("*.bak"))) == 1
        db.close()


def test_tracker_and_every_hud_box():
    img = np.zeros((560,900,3), dtype=np.uint8)
    for label in LABELS:
        f = np.array([160,110,200,240,*([0.0]*11)],dtype=np.float32)
        tracks = FaceTracker().update([f])
        tracks[0].label = label
        result = render(img, tracks, 27.0)
        assert result.shape == img.shape
        assert result.sum() > 0
    assert intersection_over_union([0,0,10,10],[5,5,10,10]) > 0


def test_multi_faces():
    f = np.array([20,20,100,100,*([0.0]*11)],dtype=np.float32)
    g = f.copy(); g[0] = 300
    tracker = FaceTracker()
    tracks = tracker.update([f,g])
    assert len(tracks) == 2
    assert {t.id for t in tracks} == {1,2}


def test_camera_sources():
    assert validate_stream_url("rtsp://example.org/live") == "rtsp://example.org/live"
    assert validate_stream_url("https://example.org/live.m3u8") == "https://example.org/live.m3u8"
    for value in ("file:///etc/passwd", "javascript:alert(1)", "https://", "http://a:b@host/a"):
        with pytest.raises(ValueError):
            validate_stream_url(value)


def test_time_and_location_metadata():
    assert clock_text({"timezone": "UNSET"}, source_is_remote=True) == "NO SIGNAL"
    assert clock_text({"show": False}) is None
    assert clock_text({"manual": True, "clock_base": "2026-11-17T10:00:00", "set_epoch": 1000}, now=1005) == "2026-11-17 10:00:05"
    assert coordinates_text({}) == "NO SIGNAL"
    assert coordinates_text({"show": False}) is None
    assert coordinates_text({"has_coordinates": True, "lat": 40.7128, "lon": -74.0060}) == "40.71° N  74.01° W"


def test_upgrade_previous_blue_labels_preserves_face_samples():
    """V2 blue labels are one designation after upgrade; backups remain intact."""
    from classifications import LEGACY_LABEL_MAP
    with tempfile.TemporaryDirectory() as folder:
        db_file = Path(folder) / "machine.db"
        old_labels = [
            "IRRELEVANT", "THREAT", "ADMIN", "PRIMARY ASSET",
            "SECONDARY ASSET", "CONTINGENCY", "ASSET", "CATALYST",
            "ANALOG INTERFACE", "ROOT", "RELEVANT-ONE", "RELEVANT-TWO",
            "RELEVANT-THREE", "RELEVANT-OTHER", "IRRELEVANT THREAT"
        ]
        allowed = ",".join(repr(x) for x in old_labels)
        with closing(sqlite3.connect(db_file)) as con, con:
            con.execute(f"CREATE TABLE people (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                        f"name TEXT NOT NULL UNIQUE, label TEXT NOT NULL CHECK(label IN ({allowed})))")
            con.execute("CREATE TABLE face_samples (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                        "person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE, "
                        "vector BLOB NOT NULL)")
            for name, label in [("蓝一", "ASSET"), ("蓝二", "CATALYST")]:
                person_id = con.execute("INSERT INTO people(name,label) VALUES(?,?)", (name, label)).lastrowid
                con.execute("INSERT INTO face_samples(person_id,vector) VALUES(?,?)",
                            (person_id, np.ones(128,dtype=np.float32).tobytes()))
            con.execute("PRAGMA user_version=2")

        db = Database(db_file)
        assert [x[2] for x in db.get_people()] == ["ASSET CATALYST", "ASSET CATALYST"]
        assert [x[3] for x in db.get_people()] == [1, 1]
        assert len(db.get_embeddings()) == 2
        assert db.connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert db.connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.connection.execute("PRAGMA user_version").fetchone()[0] == 3
        assert len(list(Path(folder).glob("*.bak"))) == 1
        with pytest.raises(ValueError, match="未知分类"):
            db.update_label(1, "ASSET")
        db.update_label(1, "ASSET CATALYST")
        db.close()
        db = Database(db_file)
        assert len(list(Path(folder).glob("*.bak"))) == 1  # no redundant migration
        db.remove(1)
        assert db.connection.execute("SELECT COUNT(*) FROM face_samples").fetchone()[0] == 1
        db.close()
