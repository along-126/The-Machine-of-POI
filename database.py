"""Local-only SQLite store for names, ONE caption per person, and face embeddings.

The original camera photos are never saved. Existing v1 databases are backed up
and migrated in place without dropping the face_samples table or its rows.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime
from pathlib import Path
import sqlite3

import numpy as np

from classifications import LABELS, LEGACY_LABEL_MAP

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "machine.db"


class Database:
    def __init__(self, db_path=DB_PATH):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.path))
        self._prepare_schema()

    def _prepare_schema(self):
        old_sql = self.connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='people'"
        ).fetchone()
        if not old_sql:
            self._create_new_tables()
            return

        # Schema v3 merges the former two blue captions into one: ASSET CATALYST.
        # The people.label CHECK constraint must be rebuilt before any row update.
        # Read-only checks happen before backup so unknown labels are never altered.
        old_labels = {row[0] for row in self.connection.execute("SELECT DISTINCT label FROM people")}
        if not old_labels.issubset(set(LABELS) | set(LEGACY_LABEL_MAP)):
            raise ValueError("数据库存在未知的身份标签；为避免损坏资料，已停止迁移。")
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version < 3 or "'ASSET CATALYST'" not in (old_sql[0] or ""):
            self._backup_and_migrate()

        with self.connection:
            self.connection.execute("PRAGMA foreign_keys = ON")
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS face_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
                    vector BLOB NOT NULL
                )
            """)
            self.connection.execute("PRAGMA user_version = 3")
        problems = self.connection.execute("PRAGMA foreign_key_check").fetchall()
        if problems:
            raise RuntimeError("人物数据库外键校验失败，请检查备份。")

    def _create_new_tables(self):
        quoted_labels = ",".join("'" + label.replace("'", "''") + "'" for label in LABELS)
        with self.connection:
            self.connection.execute(f"""
                CREATE TABLE people (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    label TEXT NOT NULL CHECK(label IN ({quoted_labels}))
                )
            """)
            self.connection.execute("""
                CREATE TABLE face_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
                    vector BLOB NOT NULL
                )
            """)
            self.connection.execute("PRAGMA foreign_keys = ON")
            self.connection.execute("PRAGMA user_version = 3")

    def _backup_and_migrate(self):
        for (label,) in self.connection.execute("SELECT DISTINCT label FROM people"):
            if label not in LEGACY_LABEL_MAP and label not in LABELS:
                raise ValueError(f"旧数据库存在未知分类 {label!r}；已停止修改。")
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup_path = self.path.with_name(f"{self.path.stem}.before-v3-{timestamp}.bak")
        # SQLite backup API safely handles WAL databases and copies all samples.
        # sqlite3.Connection's context manager commits or rolls back but does not close.
        # Explicitly close the backup connection so Windows can release its file handle.
        with closing(sqlite3.connect(str(backup_path))) as dest:
            self.connection.backup(dest)
        quoted_labels = ",".join("'" + label.replace("'", "''") + "'" for label in LABELS)
        try:
            self.connection.execute("PRAGMA foreign_keys = OFF")
            self.connection.execute("BEGIN IMMEDIATE")
            self.connection.execute(f"""
                CREATE TABLE people_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    label TEXT NOT NULL CHECK(label IN ({quoted_labels}))
                )
            """)
            # All captions converted explicitly. Face samples keep their person_id.
            rows = self.connection.execute("SELECT id, name, label FROM people").fetchall()
            converted = [(pid, name, LEGACY_LABEL_MAP.get(label, label)) for pid, name, label in rows]
            self.connection.executemany(
                "INSERT INTO people_new (id, name, label) VALUES (?, ?, ?)", converted
            )
            self.connection.execute("DROP TABLE people")
            self.connection.execute("ALTER TABLE people_new RENAME TO people")
            self.connection.execute("PRAGMA user_version = 3")
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        finally:
            self.connection.execute("PRAGMA foreign_keys = ON")
        if self.connection.execute("PRAGMA foreign_key_check").fetchone():
            raise RuntimeError(f"数据库迁移后的完整性校验失败，原备份：{backup_path}")

    @staticmethod
    def _as_blob(embedding):
        arr = np.asarray(embedding, dtype=np.float32).reshape(-1)
        if not arr.size or not np.all(np.isfinite(arr)):
            raise ValueError("无效的人脸特征。")
        norm = np.linalg.norm(arr)
        if norm <= 0:
            raise ValueError("人脸特征向量长度为零。")
        return (arr / norm).astype(np.float32).tobytes()

    def _check_other_person(self, person_id, embedding):
        """Reject the exact same face image added to two different people.

        0.97 is deliberately very high: it blocks near-identical embeddings, not
        all photos of the same person. Face verification is probabilistic.
        """
        probe = np.frombuffer(self._as_blob(embedding), dtype=np.float32)
        for other_id, other_name, _label, known in self.get_embeddings():
            if other_id != person_id and known.size == probe.size:
                if float(np.dot(probe, known)) >= 0.97:
                    raise ValueError(f"该照片人脸与已录入人物“{other_name}”高度一致，不能分配第二个身份。")

    def add_person(self, name: str, label: str, embedding):
        name = name.strip()
        if not name:
            raise ValueError("姓名不能为空。")
        if label not in LABELS:
            raise ValueError("未知分类。")
        self._check_other_person(None, embedding)
        with self.connection:
            cursor = self.connection.execute(
                "INSERT INTO people (name, label) VALUES (?, ?)", (name, label)
            )
            self.connection.execute(
                "INSERT INTO face_samples (person_id, vector) VALUES (?, ?)",
                (cursor.lastrowid, self._as_blob(embedding)),
            )
        return cursor.lastrowid

    def add_sample(self, person_id: int, embedding):
        self._check_other_person(person_id, embedding)
        with self.connection:
            self.connection.execute(
                "INSERT INTO face_samples (person_id, vector) VALUES (?, ?)",
                (person_id, self._as_blob(embedding)),
            )

    def get_people(self):
        return self.connection.execute("""
            SELECT p.id, p.name, p.label, COUNT(s.id)
            FROM people p LEFT JOIN face_samples s ON s.person_id=p.id
            GROUP BY p.id ORDER BY p.id
        """).fetchall()

    def get_embeddings(self):
        rows = self.connection.execute("""
            SELECT p.id, p.name, p.label, s.vector
            FROM people p JOIN face_samples s ON s.person_id=p.id
        """).fetchall()
        result = []
        for pid, name, label, raw in rows:
            emb = np.frombuffer(raw, dtype=np.float32)
            norm = np.linalg.norm(emb)
            if norm > 0 and np.isfinite(norm):
                result.append((pid, name, label, emb / norm))
        return result

    def update_label(self, person_id: int, label: str):
        if label not in LABELS:
            raise ValueError("未知分类。")
        with self.connection:
            self.connection.execute("UPDATE people SET label=? WHERE id=?", (label, person_id))

    def remove(self, person_id: int):
        with self.connection:
            self.connection.execute("DELETE FROM people WHERE id=?", (person_id,))

    def close(self):
        self.connection.close()
