import sqlite3#Python 自带的 SQLite 驱动
from contextlib import contextmanager #把数据库连接包装成 with 风格
from pathlib import Path  #处理数据库文件路径

from scripts.config.config import cfg #读取你在 config.py 里的配置
#python解释器：/home/luck/face3/.venv/bin/python

#放整个数据库初始化 SQL
SCHEMA = """
-- 数据库性能与安全配置
-- PRAGMA就是SQLite 的运行参数
PRAGMA journal_mode = WAL;    -- 开启预写日志，提高并发读写性能
PRAGMA synchronous = NORMAL;   -- 平衡数据安全与写入速度
PRAGMA foreign_keys = ON;      -- 强制外键约束

-- 用户主表：存储基本身份信息
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT, --用户id
    name TEXT NOT NULL, -- 用户姓名
    code TEXT NOT NULL UNIQUE, -- 唯一工号/识别码
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP -- 创建时间
);

-- 人脸特征表：存储人脸比对数据
CREATE TABLE IF NOT EXISTS face_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT, -- 人脸特征id
    user_id INTEGER NOT NULL, -- 用户id
    image_path TEXT NOT NULL,  -- 原始照片路径
    encoding TEXT NOT NULL,    -- 128维或512维特征向量(JSON字符串)
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, -- 创建时间
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE 
);

-- 考勤记录表：存储签到流水
CREATE TABLE IF NOT EXISTS attendance_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT, -- 考勤记录id
    user_id INTEGER NOT NULL, -- 用户id
    check_type TEXT NOT NULL DEFAULT 'check_in', -- 类型: check_in/check_out
    check_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    snapshot_path TEXT, -- 签到时的现场抓拍
    confidence REAL,    -- 比对置信度评分
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 索引优化：提升查询效率
CREATE INDEX IF NOT EXISTS idx_face_profiles_user_id ON face_profiles(user_id);
CREATE INDEX IF NOT EXISTS idx_attendance_records_user_id ON attendance_records(user_id);
CREATE INDEX IF NOT EXISTS idx_attendance_records_check_time ON attendance_records(check_time);
"""

#这是底层数据库管理类。怎么连数据库、怎么提交事务、怎么建表，不负责业务逻辑。
class SQLiteDB:
    #如果外部传了 db_path，就用外部的。否则用配置里的 cfg.sqlite_path
    #然后自动创建数据库所在目录，比如 data/，这样即使 data/ 还不存在，程序也能自己建出
    def __init__(self, db_path=None):
        self.db_path = Path(db_path or cfg.sqlite_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self):
        connection = sqlite3.connect(
            self.db_path,
            #数据库被占用时等多久
            timeout=cfg.sqlite_timeout,
            #是否允许跨线程使用连接
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

#对数据库增删改查的封装
class AttendanceRepository:
    def __init__(self, db=None):
        self.db = db or SQLiteDB()

    def create_user(self, name, code):
        with self.db.session() as connection:
            #code是学号，工号，编号之类
            cursor = connection.execute(
                #? 是 SQLite 的参数占位符。
                "INSERT INTO users (name, code) VALUES (?, ?)",
                #这里就是传参，用字符串拼接容易sql注入
                (name, code),
            )
            #返回刚插入这一行的主键 id
            return cursor.lastrowid
    #users 表查出所有用户
    def list_users(self):
        with self.db.session() as connection:
            rows = connection.execute(
                "SELECT id, name, code, created_at FROM users ORDER BY id DESC"
            ).fetchall()#把所有结果一次性取出来,返回的是一个列表
            #最终结果像这样：
            # [
            #     {"id": 2, "name": "李四", "code": "S002", "created_at": "..."},
            #     {"id": 1, "name": "张三", "code": "S001", "created_at": "..."}
            # ]
            return [dict(row) for row in rows]

    def save_face_profile(self, user_id, image_path, encoding):
        #这个同理
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
