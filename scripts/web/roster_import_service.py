import csv
from dataclasses import dataclass
from pathlib import Path

from scripts.config.config import cfg
from scripts.database.sqlite_db import AttendanceRepository
from scripts.web.account_security import hash_secret
from scripts.web.account_security import normalize_code
from scripts.web.account_security import normalize_name
from scripts.web.account_security import validate_initial_password


REQUIRED_COLUMNS = {"name", "code", "role", "initial_password", "status"}
ALLOWED_STATUSES = {"active", "disabled"}


@dataclass
class RosterImportSummary:
    total_rows: int
    created_count: int
    updated_count: int


class RosterImportService:
    """
    成员名单导入服务。
    当前入口是本地 CSV 文件，后续如果要换成 Excel、后台导入或管理员页面上传，只需要替换这一层。
    """

    def __init__(self, repo=None, roster_path=None):
        self.repo = repo or AttendanceRepository()
        self.roster_path = Path(roster_path or cfg.member_roster_path)

    def sync_from_file(self) -> RosterImportSummary:
        """
        把本地名单文件幂等同步到 roster_members。
        文件缺失时直接返回空摘要，保证首次拉项目时服务能先起来。
        """
        if not self.roster_path.exists():
            return RosterImportSummary(total_rows=0, created_count=0, updated_count=0)

        with self.roster_path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            header = set(reader.fieldnames or [])
            missing = REQUIRED_COLUMNS - header
            if missing:
                raise ValueError(
                    f"成员名单文件缺少列：{', '.join(sorted(missing))}。"
                )

            rows = list(reader)

        seen_codes: set[str] = set()
        created_count = 0
        updated_count = 0

        for row_index, raw_row in enumerate(rows, start=2):
            row = self._normalize_row(raw_row, row_index)
            if row["code"] in seen_codes:
                raise ValueError(f"成员名单第 {row_index} 行编号重复：{row['code']}。")
            seen_codes.add(row["code"])

            action = self.repo.upsert_roster_member(
                name=row["name"],
                code=row["code"],
                role=row["role"],
                status=row["status"],
                initial_password_hash=hash_secret(row["initial_password"]),
            )
            if action == "created":
                created_count += 1
            else:
                updated_count += 1

        return RosterImportSummary(
            total_rows=len(rows),
            created_count=created_count,
            updated_count=updated_count,
        )

    def _normalize_row(self, raw_row: dict, row_index: int) -> dict:
        """
        对每一行名单做边界校验，尽量把错误定位到具体行号，方便管理员修表。
        """
        name = normalize_name(raw_row.get("name", ""))
        code = normalize_code(raw_row.get("code", ""))
        role = normalize_name(raw_row.get("role", "")) or "member"
        initial_password = (raw_row.get("initial_password", "") or "").strip()
        status = normalize_name(raw_row.get("status", "")).lower() or "active"

        if not name:
            raise ValueError(f"成员名单第 {row_index} 行缺少姓名。")
        if not code:
            raise ValueError(f"成员名单第 {row_index} 行缺少学号或工号。")
        validate_initial_password(initial_password)
        if status not in ALLOWED_STATUSES:
            raise ValueError(
                f"成员名单第 {row_index} 行状态非法：{status}，只允许 active 或 disabled。"
            )

        return {
            "name": name,
            "code": code,
            "role": role,
            "initial_password": initial_password,
            "status": status,
        }
