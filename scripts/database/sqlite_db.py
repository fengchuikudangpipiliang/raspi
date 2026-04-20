import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from scripts.config.config import cfg


# 初始建库 SQL 只负责“新库从零创建”的完整结构。
# 已存在的旧库字段升级则交给后面的 apply_migrations 处理，避免直接破坏历史数据。
SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS roster_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    code TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL DEFAULT 'member',
    status TEXT NOT NULL DEFAULT 'active',
    initial_password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    roster_member_id INTEGER,
    name TEXT NOT NULL,
    code TEXT NOT NULL UNIQUE,
    password_hash TEXT,
    password_changed_at TEXT,
    last_login_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (roster_member_id) REFERENCES roster_members(id) ON DELETE SET NULL
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

CREATE INDEX IF NOT EXISTS idx_roster_members_status ON roster_members(status);
CREATE INDEX IF NOT EXISTS idx_face_profiles_user_id ON face_profiles(user_id);
CREATE INDEX IF NOT EXISTS idx_attendance_records_user_id ON attendance_records(user_id);
CREATE INDEX IF NOT EXISTS idx_attendance_records_check_time ON attendance_records(check_time);
"""


class SQLiteDB:
    """
    SQLite 连接与建库底座。
    这里不处理具体业务，只负责连接、事务和表结构升级。
    """

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
            self.apply_migrations(connection)

    def apply_migrations(self, connection):
        """
        给旧数据库补齐新增字段。
        这个项目目前还没有专门的 migration 框架，所以先用轻量方式托底。
        """
        self._ensure_column(connection, "users", "roster_member_id", "ALTER TABLE users ADD COLUMN roster_member_id INTEGER")
        self._ensure_column(connection, "users", "password_hash", "ALTER TABLE users ADD COLUMN password_hash TEXT")
        self._ensure_column(connection, "users", "password_changed_at", "ALTER TABLE users ADD COLUMN password_changed_at TEXT")
        self._ensure_column(connection, "users", "last_login_at", "ALTER TABLE users ADD COLUMN last_login_at TEXT")
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_roster_member_id
            ON users(roster_member_id) WHERE roster_member_id IS NOT NULL
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_roster_members_status ON roster_members(status)")

    def _ensure_column(self, connection, table_name: str, column_name: str, alter_sql: str):
        if self.column_exists(connection, table_name, column_name):
            return
        connection.execute(alter_sql)

    def column_exists(self, connection, table_name: str, column_name: str) -> bool:
        rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        return any(row["name"] == column_name for row in rows)


class AttendanceRepository:
    """
    数据访问层。
    统一封装用户、成员名单、人脸档案和考勤记录的常用数据库操作。
    """

    def __init__(self, db=None):
        self.db = db or SQLiteDB()

    def ping(self) -> bool:
        with self.db.session() as connection:
            connection.execute("SELECT 1").fetchone()
        return True

    def create_user(self, name, code, roster_member_id=None, password_hash=None):
        with self.db.session() as connection:
            cursor = connection.execute(
                """
                INSERT INTO users (roster_member_id, name, code, password_hash, password_changed_at)
                VALUES (?, ?, ?, ?, CASE WHEN ? IS NULL THEN NULL ELSE CURRENT_TIMESTAMP END)
                """,
                (roster_member_id, name, code, password_hash, password_hash),
            )
            return cursor.lastrowid

    def register_user_from_roster(self, roster_member_id: int, name: str, code: str, password_hash: str) -> dict:
        """
        用成员名单中的预置身份完成首次注册。
        如果库里已存在同编号但尚未设置密码的演示用户，则直接补齐账号字段，避免脏数据冲突。
        """
        with self.db.session() as connection:
            existing = connection.execute(
                """
                SELECT id, roster_member_id, password_hash
                FROM users
                WHERE code = ?
                """,
                (code,),
            ).fetchone()

            if existing and existing["password_hash"]:
                raise ValueError("该编号已完成注册，请直接登录。")

            if existing:
                connection.execute(
                    """
                    UPDATE users
                    SET roster_member_id = ?, name = ?, password_hash = ?, password_changed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (roster_member_id, name, password_hash, existing["id"]),
                )
                user_id = existing["id"]
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO users (roster_member_id, name, code, password_hash, password_changed_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (roster_member_id, name, code, password_hash),
                )
                user_id = cursor.lastrowid

            row = connection.execute(
                """
                SELECT
                    users.id,
                    users.roster_member_id,
                    users.name,
                    users.code,
                    users.password_hash,
                    users.password_changed_at,
                    users.last_login_at,
                    users.created_at,
                    roster_members.role AS roster_role,
                    roster_members.status AS roster_status
                FROM users
                LEFT JOIN roster_members ON roster_members.id = users.roster_member_id
                WHERE users.id = ?
                """,
                (user_id,),
            ).fetchone()
            return dict(row)

    def upsert_roster_member(self, name: str, code: str, role: str, status: str, initial_password_hash: str) -> str:
        """
        成员名单按 code 做幂等导入。
        返回 created / updated，方便启动阶段输出导入摘要。
        """
        with self.db.session() as connection:
            existing = connection.execute(
                "SELECT id FROM roster_members WHERE code = ?",
                (code,),
            ).fetchone()

            if existing:
                connection.execute(
                    """
                    UPDATE roster_members
                    SET name = ?, role = ?, status = ?, initial_password_hash = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (name, role, status, initial_password_hash, existing["id"]),
                )
                return "updated"

            connection.execute(
                """
                INSERT INTO roster_members (name, code, role, status, initial_password_hash)
                VALUES (?, ?, ?, ?, ?)
                """,
                (name, code, role, status, initial_password_hash),
            )
            return "created"

    def get_roster_member_by_code(self, code: str) -> Optional[dict]:
        with self.db.session() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    name,
                    code,
                    role,
                    status,
                    initial_password_hash,
                    created_at,
                    updated_at
                FROM roster_members
                WHERE code = ?
                """,
                (code,),
            ).fetchone()
            return dict(row) if row else None

    def list_roster_members(self):
        with self.db.session() as connection:
            rows = connection.execute(
                """
                SELECT id, name, code, role, status, created_at, updated_at
                FROM roster_members
                ORDER BY code ASC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def get_user_by_code(self, code: str) -> Optional[dict]:
        with self.db.session() as connection:
            row = connection.execute(
                """
                SELECT
                    users.id,
                    users.roster_member_id,
                    users.name,
                    users.code,
                    users.password_hash,
                    users.password_changed_at,
                    users.last_login_at,
                    users.created_at,
                    roster_members.role AS roster_role,
                    roster_members.status AS roster_status
                FROM users
                LEFT JOIN roster_members ON roster_members.id = users.roster_member_id
                WHERE users.code = ?
                """,
                (code,),
            ).fetchone()
            return dict(row) if row else None

    def get_user_by_id(self, user_id: int) -> Optional[dict]:
        with self.db.session() as connection:
            row = connection.execute(
                """
                SELECT
                    users.id,
                    users.roster_member_id,
                    users.name,
                    users.code,
                    users.password_hash,
                    users.password_changed_at,
                    users.last_login_at,
                    users.created_at,
                    roster_members.role AS roster_role,
                    roster_members.status AS roster_status
                FROM users
                LEFT JOIN roster_members ON roster_members.id = users.roster_member_id
                WHERE users.id = ?
                """,
                (user_id,),
            ).fetchone()
            return dict(row) if row else None

    def touch_user_last_login(self, user_id: int) -> None:
        with self.db.session() as connection:
            connection.execute(
                "UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?",
                (user_id,),
            )

    def list_users(self):
        with self.db.session() as connection:
            rows = connection.execute(
                """
                SELECT
                    users.id,
                    users.name,
                    users.code,
                    users.created_at,
                    roster_members.role AS roster_role,
                    roster_members.status AS roster_status
                FROM users
                LEFT JOIN roster_members ON roster_members.id = users.roster_member_id
                ORDER BY users.id DESC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def list_users_with_face_stats(self, search: str = "", status: str = "", registered_only: bool = False):
        search = (search or "").strip()
        status = (status or "").strip().lower()
        with self.db.session() as connection:
            rows = connection.execute(
                """
                SELECT
                    users.id,
                    users.roster_member_id,
                    users.name,
                    users.code,
                    users.password_hash,
                    users.password_changed_at,
                    users.last_login_at,
                    users.created_at,
                    roster_members.role AS roster_role,
                    roster_members.status AS roster_status,
                    COUNT(face_profiles.id) AS face_profiles_count
                FROM users
                LEFT JOIN roster_members ON roster_members.id = users.roster_member_id
                LEFT JOIN face_profiles ON face_profiles.user_id = users.id
                WHERE
                    (? = '' OR users.name LIKE ? OR users.code LIKE ?)
                    AND (? = '' OR IFNULL(roster_members.status, 'active') = ?)
                    AND (? = 0 OR users.password_hash IS NOT NULL)
                GROUP BY
                    users.id,
                    users.roster_member_id,
                    users.name,
                    users.code,
                    users.password_hash,
                    users.password_changed_at,
                    users.last_login_at,
                    users.created_at,
                    roster_members.role,
                    roster_members.status
                ORDER BY users.id DESC
                """,
                (
                    search,
                    f"%{search}%",
                    f"%{search}%",
                    status,
                    status,
                    1 if registered_only else 0,
                ),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_user_detail(self, user_id: int) -> Optional[dict]:
        with self.db.session() as connection:
            row = connection.execute(
                """
                SELECT
                    users.id,
                    users.roster_member_id,
                    users.name,
                    users.code,
                    users.password_hash,
                    users.password_changed_at,
                    users.last_login_at,
                    users.created_at,
                    roster_members.role AS roster_role,
                    roster_members.status AS roster_status,
                    COUNT(face_profiles.id) AS face_profiles_count
                FROM users
                LEFT JOIN roster_members ON roster_members.id = users.roster_member_id
                LEFT JOIN face_profiles ON face_profiles.user_id = users.id
                WHERE users.id = ?
                GROUP BY
                    users.id,
                    users.roster_member_id,
                    users.name,
                    users.code,
                    users.password_hash,
                    users.password_changed_at,
                    users.last_login_at,
                    users.created_at,
                    roster_members.role,
                    roster_members.status
                """,
                (user_id,),
            ).fetchone()
            return dict(row) if row else None

    def save_face_profile(self, user_id, image_path, encoding):
        with self.db.session() as connection:
            cursor = connection.execute(
                "INSERT INTO face_profiles (user_id, image_path, encoding) VALUES (?, ?, ?)",
                (user_id, image_path, encoding),
            )
            return cursor.lastrowid

    def count_face_profiles_for_user(self, user_id: int) -> int:
        with self.db.session() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM face_profiles WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            return int(row["total"])

    def list_face_profiles_for_user(self, user_id: int):
        with self.db.session() as connection:
            rows = connection.execute(
                """
                SELECT
                    face_profiles.id,
                    face_profiles.user_id,
                    users.name,
                    users.code,
                    face_profiles.image_path,
                    face_profiles.created_at
                FROM face_profiles
                JOIN users ON users.id = face_profiles.user_id
                WHERE user_id = ?
                ORDER BY face_profiles.id DESC
                """,
                (user_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_face_profiles(self, limit: int = 50, user_id: Optional[int] = None, code: str = ""):
        code = (code or "").strip()
        with self.db.session() as connection:
            rows = connection.execute(
                """
                SELECT
                    face_profiles.id,
                    face_profiles.user_id,
                    users.name,
                    users.code,
                    face_profiles.image_path,
                    face_profiles.created_at
                FROM face_profiles
                JOIN users ON users.id = face_profiles.user_id
                WHERE
                    (? IS NULL OR face_profiles.user_id = ?)
                    AND (? = '' OR users.code = ?)
                ORDER BY face_profiles.id DESC
                LIMIT ?
                """,
                (user_id, user_id, code, code, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_face_profile_by_id(self, face_profile_id: int) -> Optional[dict]:
        with self.db.session() as connection:
            row = connection.execute(
                """
                SELECT
                    face_profiles.id,
                    face_profiles.user_id,
                    users.name,
                    users.code,
                    face_profiles.image_path,
                    face_profiles.encoding,
                    face_profiles.created_at
                FROM face_profiles
                JOIN users ON users.id = face_profiles.user_id
                WHERE face_profiles.id = ?
                """,
                (face_profile_id,),
            ).fetchone()
            return dict(row) if row else None

    def delete_face_profile(self, face_profile_id: int) -> bool:
        with self.db.session() as connection:
            cursor = connection.execute(
                "DELETE FROM face_profiles WHERE id = ?",
                (face_profile_id,),
            )
            return cursor.rowcount > 0

    def update_user_password_hash(self, user_id: int, password_hash: str) -> bool:
        with self.db.session() as connection:
            cursor = connection.execute(
                """
                UPDATE users
                SET password_hash = ?, password_changed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (password_hash, user_id),
            )
            return cursor.rowcount > 0

    def update_user_roster_status(self, user_id: int, status: str) -> bool:
        with self.db.session() as connection:
            cursor = connection.execute(
                """
                UPDATE roster_members
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = (
                    SELECT roster_member_id
                    FROM users
                    WHERE id = ?
                )
                """,
                (status, user_id),
            )
            return cursor.rowcount > 0

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

    def list_attendance_records(self, limit=50, date: str = "", code: str = "", name: str = ""):
        date = (date or "").strip()
        code = (code or "").strip()
        name = (name or "").strip()
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
                WHERE
                    (? = '' OR date(attendance_records.check_time, 'localtime') = ?)
                    AND (? = '' OR users.code = ?)
                    AND (? = '' OR users.name LIKE ?)
                ORDER BY attendance_records.id DESC
                LIMIT ?
                """,
                (
                    date,
                    date,
                    code,
                    code,
                    name,
                    f"%{name}%",
                    limit,
                ),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_attendance_record_by_id(self, attendance_id: int) -> Optional[dict]:
        with self.db.session() as connection:
            row = connection.execute(
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
                WHERE attendance_records.id = ?
                """,
                (attendance_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_attendance_summary(self, date: str = "") -> dict:
        date = (date or "").strip()
        with self.db.session() as connection:
            attendance_clause = ""
            params: tuple = ()
            if date:
                attendance_clause = "WHERE date(check_time, 'localtime') = ?"
                params = (date,)

            total_users_row = connection.execute("SELECT COUNT(*) AS total FROM users").fetchone()
            checked_in_row = connection.execute(
                f"""
                SELECT COUNT(DISTINCT user_id) AS total
                FROM attendance_records
                {attendance_clause}
                """,
                params,
            ).fetchone()
            record_count_row = connection.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM attendance_records
                {attendance_clause}
                """,
                params,
            ).fetchone()
            return {
                "date": date,
                "registered_users": int(total_users_row["total"]),
                "checked_in_users": int(checked_in_row["total"]),
                "attendance_records": int(record_count_row["total"]),
                "absent_users": max(int(total_users_row["total"]) - int(checked_in_row["total"]), 0),
            }


def init_db():
    db = SQLiteDB()
    db.init_schema()
    return db
