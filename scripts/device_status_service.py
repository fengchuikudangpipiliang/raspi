import os
import socket
import time
from datetime import datetime
from pathlib import Path

from scripts.config.config import cfg
from scripts.database.sqlite_db import AttendanceRepository


class DeviceStatusService:
    """
    设备状态服务。
    负责汇总树莓派本机、摄像头线程和数据库的健康状态，给管理员 API 直接复用。
    """

    def __init__(self, camera, repo=None, started_at=None):
        self.camera = camera
        self.repo = repo or AttendanceRepository()
        self.started_at = started_at or time.time()

    def build_device_info(self) -> dict:
        return {
            "device_id": cfg.device_id,
            "device_name": cfg.device_name,
            "device_location": cfg.device_location,
            "app_name": cfg.app_name,
            "hostname": socket.gethostname(),
            "fqdn": socket.getfqdn(),
            "web_host": cfg.web_host,
            "web_port": cfg.web_port,
            "started_at": self._iso_from_timestamp(self.started_at),
            "server_time": self._iso_now(),
            "attendance_policy": self._build_attendance_policy(),
        }

    def build_health(self) -> dict:
        database_ok = self._check_database()
        health = {
            **self.build_device_info(),
            "app_uptime_seconds": round(max(time.time() - self.started_at, 0.0), 3),
            "database": {
                "ok": database_ok,
                "sqlite_path": cfg.sqlite_path,
            },
            "camera": {
                "configured": True,
                "running": bool(self.camera.running),
                "last_frame_at": self._iso_from_timestamp(self.camera.last_frame_at),
                "last_opened_at": self._iso_from_timestamp(self.camera.last_opened_at),
                "last_error": self.camera.last_error,
                "detected_faces": len(getattr(self.camera, "face_locations", []) or []),
                "known_faces_count": 0 if getattr(self.camera, "recognizer", None) is None else self.camera.recognizer.known_faces_count(),
                "last_attendance_message": getattr(self.camera, "last_attendance_message", None),
                "last_attendance_record": getattr(self.camera, "last_attendance_record", None),
                "last_policy_event": getattr(self.camera, "last_policy_event", None),
            },
            "files": {
                "roster_exists": Path(cfg.member_roster_path).exists(),
                "faces_dir_exists": Path(cfg.faces_dir).exists(),
                "snapshots_dir_exists": Path(cfg.snapshots_dir).exists(),
            },
            "admin_api": {
                "token_configured": bool((cfg.admin_api_token or "").strip()),
                "using_default_token": (cfg.admin_api_token or "").strip() == "face3-admin-change-this-token",
            },
        }
        health["ok"] = health["database"]["ok"]
        return health

    def build_metrics(self) -> dict:
        disk_usage = self._read_disk_usage(Path(cfg.sqlite_path).resolve().parent)
        system_uptime_seconds = self._read_system_uptime_seconds()
        memory = self._read_memory_metrics()
        return {
            **self.build_device_info(),
            "system_uptime_seconds": system_uptime_seconds,
            "app_uptime_seconds": round(max(time.time() - self.started_at, 0.0), 3),
            "load_average": self._read_load_average(),
            "memory": memory,
            "disk": disk_usage,
            "temperature": {
                "cpu_celsius": self._read_cpu_temperature_celsius(),
            },
            "process": {
                "pid": os.getpid(),
            },
            "attendance_policy": self._build_attendance_policy(),
        }

    def _check_database(self) -> bool:
        try:
            return self.repo.ping()
        except Exception:
            return False

    def _read_load_average(self) -> dict:
        try:
            one, five, fifteen = os.getloadavg()
            return {
                "one_min": round(one, 3),
                "five_min": round(five, 3),
                "fifteen_min": round(fifteen, 3),
            }
        except Exception:
            return {
                "one_min": None,
                "five_min": None,
                "fifteen_min": None,
            }

    def _read_memory_metrics(self) -> dict:
        meminfo_path = Path("/proc/meminfo")
        if not meminfo_path.exists():
            return {
                "total_bytes": None,
                "available_bytes": None,
                "used_bytes": None,
                "usage_percent": None,
            }

        values: dict[str, int] = {}
        for line in meminfo_path.read_text(encoding="utf-8").splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            number = value.strip().split()[0]
            if number.isdigit():
                values[key] = int(number) * 1024

        total = values.get("MemTotal")
        available = values.get("MemAvailable")
        if not total or available is None:
            return {
                "total_bytes": total,
                "available_bytes": available,
                "used_bytes": None if total is None else max(total - (available or 0), 0),
                "usage_percent": None,
            }

        used = max(total - available, 0)
        return {
            "total_bytes": total,
            "available_bytes": available,
            "used_bytes": used,
            "usage_percent": round((used / total) * 100.0, 2) if total else None,
        }

    def _read_disk_usage(self, target: Path) -> dict:
        target.mkdir(parents=True, exist_ok=True)
        usage = os.statvfs(str(target))
        total = usage.f_blocks * usage.f_frsize
        available = usage.f_bavail * usage.f_frsize
        used = max(total - available, 0)
        return {
            "path": str(target),
            "total_bytes": total,
            "available_bytes": available,
            "used_bytes": used,
            "usage_percent": round((used / total) * 100.0, 2) if total else None,
        }

    def _read_cpu_temperature_celsius(self):
        thermal_path = Path("/sys/class/thermal/thermal_zone0/temp")
        if not thermal_path.exists():
            return None
        try:
            return round(int(thermal_path.read_text(encoding="utf-8").strip()) / 1000.0, 2)
        except Exception:
            return None

    def _read_system_uptime_seconds(self):
        uptime_path = Path("/proc/uptime")
        if not uptime_path.exists():
            return None
        try:
            return round(float(uptime_path.read_text(encoding="utf-8").split()[0]), 3)
        except Exception:
            return None

    def _iso_now(self) -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    def _iso_from_timestamp(self, value):
        if value is None:
            return None
        return datetime.fromtimestamp(value).astimezone().isoformat(timespec="seconds")

    def _build_attendance_policy(self) -> dict:
        """
        汇总当前生效的考勤规则配置，方便管理员端解释写库或拦截原因。
        """

        return {
            "rule_mode": str(cfg.attendance_rule_mode or "daily_once").strip().lower(),
            "duplicate_block_seconds": max(int(cfg.attendance_duplicate_block_seconds or 0), 0),
            "daily_check_in_limit": max(int(cfg.attendance_daily_check_in_limit or 1), 1),
            "policy_feedback_seconds": max(int(cfg.attendance_policy_feedback_seconds or 0), 0),
            "attendance_window": {
                "start_time": cfg.attendance_start_time,
                "end_time": cfg.attendance_end_time,
            },
            "testing_friendly": str(cfg.attendance_rule_mode or "").strip().lower() == "interval_only",
        }
