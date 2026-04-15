import sqlite3
from contextlib import contextmanager
from pathlib import Path

from scripts.config.config import cfg


SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    code TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS face_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    image_path TEXT NOT NULL,
    encoding TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS attendance_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    check_type TEXT NOT NULL DEFAULT 'check_in',
    check_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    snapshot_path TEXT,
    confidence REAL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_face_profiles_user_id ON face_profiles(user_id);
CREATE INDEX IF NOT EXISTS idx_attendance_records_user_id ON attendance_records(user_id);
CREATE INDEX IF NOT EXISTS idx_attendance_records_check_time ON attendance_records(check_time);
"""


class SQLiteDB:
    def __init__(self, db_path=None):
        self.db_path = Path(db_path or cfg.sqlite_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self):
        connection = sqlite3.connect(
            self.db_path,
            timeout=cfg.sqlite_timeout,
            check_same_thread=cfg.sqlite_check_same_thread,
        )
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA foreign_keys = {'ON' if cfg.sqlite_foreign_keys else 'OFF'};")
        return connection

    @contextmanager
    def session(self):
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def init_schema(self):
        with self.session() as connection:
            connection.executescript(SCHEMA)


class AttendanceRepository:
    def __init__(self, db=None):
        self.db = db or SQLiteDB()

    def create_user(self, name, code):
        with self.db.session() as connection:
            cursor = connection.execute(
                "INSERT INTO users (name, code) VALUES (?, ?)",
                (name, code),
            )
            return cursor.lastrowid

    def list_users(self):
        with self.db.session() as connection:
            rows = connection.execute(
                "SELECT id, name, code, created_at FROM users ORDER BY id DESC"
            ).fetchall()
            return [dict(row) for row in rows]

    def save_face_profile(self, user_id, image_path, encoding):
        with self.db.session() as connection:
            cursor = connection.execute(
                "INSERT INTO face_profiles (user_id, image_path, encoding) VALUES (?, ?, ?)",
                (user_id, image_path, encoding),
            )
            return cursor.lastrowid

    def create_attendance_record(self, user_id, check_type="check_in", snapshot_path=None, confidence=None):
        with self.db.session() as connection:
            cursor = connection.execute(
                """
                INSERT INTO attendance_records (user_id, check_type, snapshot_path, confidence)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, check_type, snapshot_path, confidence),
            )
            return cursor.lastrowid

    def list_attendance_records(self, limit=50):
        with self.db.session() as connection:
            rows = connection.execute(
                """
                SELECT
                    attendance_records.id,
                    attendance_records.user_id,
                    users.name,
                    users.code,
                    attendance_records.check_type,
                    attendance_records.check_time,
                    attendance_records.snapshot_path,
                    attendance_records.confidence
                FROM attendance_records
                JOIN users ON users.id = attendance_records.user_id
                ORDER BY attendance_records.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]


def init_db():
    db = SQLiteDB()
    db.init_schema()
    return db
