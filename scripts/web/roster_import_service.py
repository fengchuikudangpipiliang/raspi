import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from scripts.config.config import cfg
from scripts.database.sqlite_db import AttendanceRepository
from scripts.web.account_security import hash_secret
from scripts.web.account_security import normalize_code
from scripts.web.account_security import normalize_name
from scripts.web.account_security import validate_initial_password


REQUIRED_COLUMNS = {"name", "code", "role", "initial_password", "status"}
ALLOWED_STATUSES = {"active", "disabled"}
CSV_FIELDNAMES = ["name", "code", "role", "initial_password", "status"]


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
        self._last_synced_signature = None

    def sync_from_file(self) -> RosterImportSummary:
        """
        把本地名单文件幂等同步到 roster_members。
        文件缺失时直接返回空摘要，保证首次拉项目时服务能先起来。
        """
        if not self.roster_path.exists():
            self._last_synced_signature = None
            return RosterImportSummary(total_rows=0, created_count=0, updated_count=0)

        rows = self._load_rows_from_file()

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

        summary = RosterImportSummary(
            total_rows=len(rows),
            created_count=created_count,
            updated_count=updated_count,
        )
        self._last_synced_signature = self._get_file_signature()
        return summary

    def sync_from_file_if_changed(self) -> dict:
        """
        只有当 CSV 文件真的发生变化时才重新同步。
        这样管理员手工改 CSV 后，不用重启服务也能让名单查询和注册逻辑看到新数据。
        """
        current_signature = self._get_file_signature()
        if current_signature is None:
            self._last_synced_signature = None
            return {
                "synced": False,
                "summary": RosterImportSummary(total_rows=0, created_count=0, updated_count=0),
            }
        if self._last_synced_signature == current_signature:
            return {
                "synced": False,
                "summary": RosterImportSummary(total_rows=0, created_count=0, updated_count=0),
            }

        summary = self.sync_from_file()
        return {
            "synced": True,
            "summary": summary,
        }

    def create_member(
        self,
        *,
        name: str,
        code: str,
        role: str,
        status: str,
        initial_password: str,
    ) -> dict:
        """
        从管理员 API 新增名单成员。
        新数据会同时写回 CSV 和 SQLite，避免“文件和数据库各自一套”的状态漂移。
        """
        normalized_row = self._normalize_admin_row(
            name=name,
            code=code,
            role=role,
            status=status,
            initial_password=initial_password,
            require_initial_password=True,
        )
        self.sync_from_file_if_changed()
        if self.repo.get_roster_member_by_code(normalized_row["code"]):
            raise ValueError("该学号或工号已存在，请改用更新接口。")

        rows = self._load_rows_from_file(allow_missing=True)
        if any(normalize_code(item.get("code", "")) == normalized_row["code"] for item in rows):
            raise ValueError("CSV 里已存在同编号成员，请改用更新接口。")

        rows.append(normalized_row)
        self._save_rows_to_file(rows)
        action = self.repo.upsert_roster_member(
            name=normalized_row["name"],
            code=normalized_row["code"],
            role=normalized_row["role"],
            status=normalized_row["status"],
            initial_password_hash=hash_secret(normalized_row["initial_password"]),
        )
        member = self.repo.get_roster_member_by_code(normalized_row["code"])
        return {
            "action": action,
            "member": member,
        }

    def update_member(
        self,
        roster_member_id: int,
        *,
        name: str,
        role: str,
        status: str,
        initial_password: str = "",
        code: str = "",
    ) -> dict:
        """
        从管理员 API 更新现有名单成员。
        当前刻意不支持改编号，避免 users、face_profiles 等关联链路被意外打断。
        """
        self.sync_from_file_if_changed()
        existing_member = self.repo.get_roster_member_by_id(roster_member_id)
        if not existing_member:
            raise ValueError("成员名单不存在。")

        incoming_code = normalize_code(code or existing_member["code"])
        if incoming_code != existing_member["code"]:
            raise ValueError("当前版本不支持直接修改学号或工号，请新建正确成员后再处理旧记录。")

        rows = self._load_rows_from_file(allow_missing=True)
        row_index = self._find_row_index_by_code(rows, existing_member["code"])
        preserved_password = ""
        if row_index is not None:
            preserved_password = (rows[row_index].get("initial_password", "") or "").strip()

        normalized_row = self._normalize_admin_row(
            name=name,
            code=existing_member["code"],
            role=role,
            status=status,
            initial_password=initial_password or preserved_password,
            require_initial_password=not bool(preserved_password),
        )
        if not normalized_row["initial_password"]:
            raise ValueError("缺少初始密码，无法把更新内容写回 CSV，请补充 initial_password。")

        if row_index is None:
            rows.append(normalized_row)
        else:
            rows[row_index] = normalized_row

        self._save_rows_to_file(rows)
        action = self.repo.upsert_roster_member(
            name=normalized_row["name"],
            code=normalized_row["code"],
            role=normalized_row["role"],
            status=normalized_row["status"],
            initial_password_hash=hash_secret(normalized_row["initial_password"]),
        )
        member = self.repo.get_roster_member_by_id(roster_member_id)
        return {
            "action": action,
            "member": member,
        }

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

    def _normalize_admin_row(
        self,
        *,
        name: str,
        code: str,
        role: str,
        status: str,
        initial_password: str,
        require_initial_password: bool,
    ) -> dict:
        """
        统一处理管理员 API 传入的名单字段，和 CSV 导入保持同一套规则。
        """
        normalized_name = normalize_name(name)
        normalized_code = normalize_code(code)
        normalized_role = normalize_name(role) or "member"
        normalized_status = normalize_name(status).lower() or "active"
        normalized_initial_password = (initial_password or "").strip()

        if not normalized_name:
            raise ValueError("姓名不能为空。")
        if not normalized_code:
            raise ValueError("学号或工号不能为空。")
        if normalized_status not in ALLOWED_STATUSES:
            raise ValueError("状态只允许 active 或 disabled。")
        if require_initial_password and not normalized_initial_password:
            raise ValueError("初始密码不能为空。")
        if normalized_initial_password:
            validate_initial_password(normalized_initial_password)

        return {
            "name": normalized_name,
            "code": normalized_code,
            "role": normalized_role,
            "status": normalized_status,
            "initial_password": normalized_initial_password,
        }

    def _load_rows_from_file(self, allow_missing: bool = False) -> list[dict]:
        """
        读取原始 CSV 行，供热同步和管理员修改共用。
        """
        if not self.roster_path.exists():
            if allow_missing:
                return []
            raise ValueError(f"成员名单文件不存在：{self.roster_path}。")

        with self.roster_path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            header = set(reader.fieldnames or [])
            missing = REQUIRED_COLUMNS - header
            if missing:
                raise ValueError(
                    f"成员名单文件缺少列：{', '.join(sorted(missing))}。"
                )
            return list(reader)

    def _save_rows_to_file(self, rows: list[dict]) -> None:
        """
        用原子替换方式重写 CSV，尽量避免写一半时文件损坏。
        """
        self.roster_path.parent.mkdir(parents=True, exist_ok=True)
        normalized_rows = sorted(
            [
                {
                    "name": normalize_name(row.get("name", "")),
                    "code": normalize_code(row.get("code", "")),
                    "role": normalize_name(row.get("role", "")) or "member",
                    "initial_password": (row.get("initial_password", "") or "").strip(),
                    "status": normalize_name(row.get("status", "")).lower() or "active",
                }
                for row in rows
            ],
            key=lambda item: item["code"],
        )

        temp_path = self.roster_path.with_suffix(f"{self.roster_path.suffix}.tmp")
        with temp_path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=CSV_FIELDNAMES)
            writer.writeheader()
            writer.writerows(normalized_rows)

        temp_path.replace(self.roster_path)
        self._last_synced_signature = self._get_file_signature()

    def _find_row_index_by_code(self, rows: list[dict], code: str) -> Optional[int]:
        normalized_code = normalize_code(code)
        for index, row in enumerate(rows):
            if normalize_code(row.get("code", "")) == normalized_code:
                return index
        return None

    def _get_file_signature(self):
        if not self.roster_path.exists():
            return None
        stat = self.roster_path.stat()
        return (
            stat.st_mtime_ns,
            stat.st_size,
        )
