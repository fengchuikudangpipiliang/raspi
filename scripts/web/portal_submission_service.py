import base64
import binascii
import json
import re
from datetime import timedelta
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

from scripts.config.config import cfg
from scripts.database.sqlite_db import AttendanceRepository
from scripts.web.account_security import hash_secret
from scripts.web.account_security import normalize_code
from scripts.web.account_security import normalize_name
from scripts.web.account_security import validate_new_password
from scripts.web.account_security import verify_secret
from scripts.web.roster_import_service import RosterImportService
from scripts.web.registration_validation import RegistrationValidationPipeline
from scripts.web.registration_validation import extract_face_encoding
from scripts.web.registration_validation import results_to_dicts


ALLOWED_IMAGE_TYPES = {"jpeg", "png", "webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024


class PortalAccountService:
    """
    外网用户门户服务。
    负责首次注册、登录校验、登录态读取和人脸上传入库。
    """

    def __init__(self, repo=None, validation_pipeline=None, roster_import_service=None):
        self.repo = repo or AttendanceRepository()
        self.validation_pipeline = validation_pipeline or RegistrationValidationPipeline()
        self.roster_import_service = roster_import_service or RosterImportService(repo=self.repo)
        self.faces_dir = Path(cfg.faces_dir)
        self.faces_dir.mkdir(parents=True, exist_ok=True)
        self.max_face_profiles = max(int(cfg.portal_max_face_profiles), 1)
        self.face_reupload_cooldown_seconds = max(int(cfg.portal_face_reupload_cooldown_seconds), 0)

    def register_member(
        self,
        full_name: str,
        code: str,
        initial_password: str,
        new_password: str,
        confirm_password: str,
    ) -> dict:
        """
        首次注册必须经过“名单存在 + 初始密码正确 + 新密码合格”三重门禁。
        """
        normalized_name = normalize_name(full_name)
        normalized_code = normalize_code(code)
        initial_password = (initial_password or "").strip()
        if len(normalized_name) < 2:
            raise ValueError("姓名至少需要 2 个字符。")
        if not normalized_code:
            raise ValueError("请填写学号或工号。")
        if not initial_password:
            raise ValueError("请填写管理员预置的初始密码。")

        self.roster_import_service.sync_from_file_if_changed()
        roster_member = self.repo.get_roster_member_by_code(normalized_code)
        if not roster_member:
            raise ValueError("该学号或工号不在允许注册名单中，请联系管理员。")
        if roster_member["status"] != "active":
            raise ValueError("该账号当前不可注册，请联系管理员确认名单状态。")
        if normalize_name(roster_member["name"]) != normalized_name:
            raise ValueError("姓名与预置名单不匹配，请确认后重试。")

        existing_user = self.repo.get_user_by_code(normalized_code)
        if existing_user and existing_user.get("password_hash"):
            raise ValueError("该账号已完成注册，请直接登录。")
        if not verify_secret(initial_password, roster_member["initial_password_hash"]):
            raise ValueError("初始密码错误，请联系管理员确认。")

        validated_password = validate_new_password(
            code=normalized_code,
            name=normalized_name,
            initial_password=initial_password,
            new_password=new_password,
            confirm_password=confirm_password,
        )
        password_hash = hash_secret(validated_password)
        return self.repo.register_user_from_roster(
            roster_member_id=roster_member["id"],
            name=roster_member["name"],
            code=roster_member["code"],
            password_hash=password_hash,
        )

    def login_user(self, code: str, password: str) -> dict:
        """
        登录只认首次注册后写入 users 的正式密码，不再认初始密码。
        """
        normalized_code = normalize_code(code)
        password = (password or "").strip()
        if not normalized_code:
            raise ValueError("请填写学号或工号。")
        if not password:
            raise ValueError("请输入密码。")

        self.roster_import_service.sync_from_file_if_changed()
        user = self.repo.get_user_by_code(normalized_code)
        if not user or not user.get("password_hash"):
            roster_member = self.repo.get_roster_member_by_code(normalized_code)
            if roster_member:
                raise ValueError("该账号尚未完成首次注册，请先使用初始密码注册。")
            raise ValueError("账号或密码错误。")
        if user.get("roster_status") not in (None, "active"):
            raise ValueError("该账号已被停用，请联系管理员。")
        if not verify_secret(password, user["password_hash"]):
            raise ValueError("账号或密码错误。")

        self.repo.touch_user_last_login(user["id"])
        return self.repo.get_user_by_id(user["id"])

    def require_user(self, user_id: int) -> Optional[dict]:
        """
        统一读取当前登录用户，并顺手把基础人脸状态补齐给页面。
        """
        user = self.repo.get_user_by_id(user_id)
        if not user or not user.get("password_hash"):
            return None

        face_profiles = self.repo.list_face_profiles_for_user(user_id)
        user["face_profiles"] = face_profiles
        user["face_profiles_count"] = len(face_profiles)
        user["approved_face_profiles_count"] = sum(1 for item in face_profiles if item.get("review_status") == "approved")
        user["pending_face_profiles_count"] = sum(1 for item in face_profiles if item.get("review_status") == "pending")
        user["rejected_face_profiles_count"] = sum(1 for item in face_profiles if item.get("review_status") == "rejected")
        user["face_profile_ready"] = bool(face_profiles)
        latest_face_profile = face_profiles[0] if face_profiles else None
        user["latest_face_profile"] = latest_face_profile
        review_status = (latest_face_profile or {}).get("review_status") or ""
        user["latest_face_review_status"] = review_status
        user["latest_face_review_status_label"] = self._get_review_status_label(review_status)
        user["latest_face_review_status_tone"] = self._get_review_status_tone(review_status)
        user["latest_face_review_comment"] = (latest_face_profile or {}).get("review_comment") or ""
        user["latest_face_reviewed_at"] = (latest_face_profile or {}).get("reviewed_at")
        user["face_profile_recognition_ready"] = user["approved_face_profiles_count"] > 0
        cooldown = self.get_face_reupload_cooldown(user_id)
        user["face_reupload_cooldown_remaining_seconds"] = cooldown["remaining_seconds"]
        user["face_reupload_allowed"] = cooldown["allowed"]
        user["face_reupload_locked_until"] = cooldown["locked_until"]
        user["face_reupload_message"] = cooldown["message"]
        user["face_review_hint"] = self._build_face_review_hint(user)
        return user

    def get_face_reupload_cooldown(self, user_id: int) -> dict:
        """
        计算当前账号距离下次允许重新上传人脸照片还剩多久。
        只要已经成功上传过一张，就按最近一次上传时间进入冷却。
        """
        face_profiles = self.repo.list_face_profiles_for_user(user_id)
        if not face_profiles or self.face_reupload_cooldown_seconds <= 0:
            return {
                "allowed": True,
                "remaining_seconds": 0,
                "locked_until": None,
                "message": "",
            }

        latest_profile = face_profiles[0]
        created_at = self._parse_local_datetime(latest_profile.get("created_at"))
        if created_at is None:
            return {
                "allowed": True,
                "remaining_seconds": 0,
                "locked_until": None,
                "message": "",
            }

        unlock_at = created_at + timedelta(seconds=self.face_reupload_cooldown_seconds)
        now = datetime.now().astimezone()
        remaining_seconds = max(int((unlock_at - now).total_seconds()), 0)
        if remaining_seconds <= 0:
            return {
                "allowed": True,
                "remaining_seconds": 0,
                "locked_until": unlock_at.strftime("%Y-%m-%d %H:%M:%S"),
                "message": "",
            }

        return {
            "allowed": False,
            "remaining_seconds": remaining_seconds,
            "locked_until": unlock_at.strftime("%Y-%m-%d %H:%M:%S"),
            "message": f"距离下次重新上传还需等待 {self._format_seconds(remaining_seconds)}",
        }

    def submit_face_profile(self, user_id: int, image_data: str) -> dict:
        """
        登录用户上传一张注册照。
        这里复用现有质量校验流水线，合格后才提取编码并入库。
        """
        image_bytes, image_type = decode_image_data(image_data)
        return self.submit_face_profile_from_bytes(user_id, image_bytes, image_type)

    def submit_face_profile_from_bytes(self, user_id: int, image_bytes: bytes, image_type: str) -> dict:
        """
        直接消费后端已经拿到的可信抓拍结果。
        这样可以复用到动作挑战链路，避免前端在通过挑战后再偷偷换图。
        """
        user = self.require_user(user_id)
        if not user:
            raise ValueError("登录状态已失效，请重新登录。")
        if user["face_profile_ready"] and not user["face_reupload_allowed"]:
            raise ValueError(user["face_reupload_message"] or "当前还不能重新上传人脸照片。")
        if user["face_profiles_count"] >= self.max_face_profiles:
            raise ValueError(f"当前账号最多只允许保存 {self.max_face_profiles} 份人脸档案。")

        context, passed, validation_results = self.validation_pipeline.validate_with_context(image_bytes)
        validation_payload = results_to_dicts(validation_results)
        if not passed:
            return {
                "ok": False,
                "message": "照片未通过质量校验，请重新拍摄更清晰的正脸照片。",
                "validation_results": validation_payload,
            }

        encoding = extract_face_encoding(context)
        image_path = self._save_face_image(user["code"], image_bytes, image_type)
        face_profile_id = self.repo.save_face_profile(
            user_id=user["id"],
            image_path=image_path,
            encoding=json.dumps(encoding.tolist(), ensure_ascii=False),
        )

        refreshed_user = self.require_user(user["id"])
        return {
            "ok": True,
            "message": "人脸资料已提交，等待管理员审核。审核通过后才会用于终端识别。",
            "face_profile_id": face_profile_id,
            "submission_id": f"face-profile-{face_profile_id}",
            "image_path": image_path,
            "validation_results": validation_payload,
            "face_profiles_count": refreshed_user["face_profiles_count"],
            "review_status": refreshed_user["latest_face_review_status"],
        }

    def _parse_local_datetime(self, value: Optional[str]) -> Optional[datetime]:
        text = (value or "").strip()
        if not text:
            return None
        try:
            return datetime.strptime(text, "%Y-%m-%d %H:%M:%S").astimezone()
        except ValueError:
            return None

    def _format_seconds(self, seconds: int) -> str:
        total = max(int(seconds), 0)
        minutes, secs = divmod(total, 60)
        hours, minutes = divmod(minutes, 60)
        parts: list[str] = []
        if hours:
            parts.append(f"{hours} 小时")
        if minutes:
            parts.append(f"{minutes} 分钟")
        if secs and not hours:
            parts.append(f"{secs} 秒")
        return "".join(parts) or "0 秒"

    def _get_review_status_label(self, status: str) -> str:
        """
        把数据库中的审核状态翻译成页面上更直观的中文文案。
        """

        mapping = {
            "pending": "待管理员审核",
            "approved": "审核通过",
            "rejected": "审核未通过",
        }
        return mapping.get((status or "").strip().lower(), "未上传")

    def _get_review_status_tone(self, status: str) -> str:
        """
        返回页面状态胶囊使用的语义色。
        """

        mapping = {
            "pending": "working",
            "approved": "ok",
            "rejected": "fail",
        }
        return mapping.get((status or "").strip().lower(), "warning")

    def _build_face_review_hint(self, user: dict) -> str:
        """
        基于最近一次上传和审核结果，拼装用户中心要展示的状态说明。
        """

        if not user.get("latest_face_profile"):
            return "尚未提交人脸照片。"

        status = (user.get("latest_face_review_status") or "").strip().lower()
        if status == "approved":
            reviewed_at = user.get("latest_face_reviewed_at")
            if reviewed_at:
                return f"最近一张照片已审核通过，终端识别可使用这份档案。审核时间：{reviewed_at}"
            return "最近一张照片已审核通过，终端识别可使用这份档案。"
        if status == "rejected":
            comment = user.get("latest_face_review_comment") or "请重新拍摄更清晰的正脸照片后再次提交。"
            if int(user.get("approved_face_profiles_count") or 0) > 0:
                return f"最近一张照片未通过审核。{comment} 当前终端仍会继续使用之前已通过审核的照片。"
            return f"最近一张照片未通过审核。{comment}"
        if int(user.get("approved_face_profiles_count") or 0) > 0:
            return "最近一张照片已提交，正在等待管理员审核。当前终端仍会继续使用之前已通过审核的照片。"
        return "最近一张照片已提交，正在等待管理员审核。"

    def decode_register_payload(self, payload: dict) -> dict:
        """
        对注册接口输入做最小清洗，避免路由层堆大量字符串处理逻辑。
        """
        if not isinstance(payload, dict):
            raise ValueError("提交数据格式错误。")
        return {
            "full_name": normalize_name(payload.get("full_name", "")),
            "code": normalize_code(payload.get("code", "")),
            "initial_password": (payload.get("initial_password", "") or "").strip(),
            "new_password": (payload.get("new_password", "") or "").strip(),
            "confirm_password": (payload.get("confirm_password", "") or "").strip(),
        }

    def decode_login_payload(self, payload: dict) -> dict:
        """
        登录接口的轻量输入清洗。
        """
        if not isinstance(payload, dict):
            raise ValueError("提交数据格式错误。")
        return {
            "code": normalize_code(payload.get("code", "")),
            "password": (payload.get("password", "") or "").strip(),
        }

    def decode_face_payload(self, payload: dict) -> dict:
        """
        人脸上传接口的输入清洗。
        """
        if not isinstance(payload, dict):
            raise ValueError("提交数据格式错误。")
        image_data = payload.get("image_data", "")
        if not image_data:
            raise ValueError("请先选择或拍摄一张照片。")
        return {"image_data": image_data}

    def decode_challenge_submission_payload(self, payload: dict) -> dict:
        """
        兼容 Funnel 动作挑战页最终提交的数据结构。
        当前登录用户的姓名和编号以后端账号为准，前端只负责补充挑战结果和授权勾选。
        """
        if not isinstance(payload, dict):
            raise ValueError("提交数据格式错误。")

        challenge_id = normalize_code(payload.get("challenge_id", ""))
        if not challenge_id:
            raise ValueError("请先完成动作活体挑战。")
        if not payload.get("consent"):
            raise ValueError("请先勾选授权说明后再提交。")

        return {
            "challenge_id": challenge_id.lower(),
            "phone": normalize_name(payload.get("phone", ""))[:20],
            "notes": normalize_name(payload.get("notes", ""))[:200],
            "consent": True,
        }

    def _save_face_image(self, code: str, image_bytes: bytes, image_type: str) -> str:
        """
        把通过校验的原图落盘到用户专属目录，便于后续审核和追溯。
        """
        user_dir = self.faces_dir / normalize_code(code)
        user_dir.mkdir(parents=True, exist_ok=True)
        file_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}.{image_type}"
        image_path = user_dir / file_name
        image_path.write_bytes(image_bytes)
        try:
            return str(image_path.relative_to(Path.cwd()))
        except ValueError:
            return str(image_path)


def decode_image_data(data_url: str) -> tuple[bytes, str]:
    """
    解码前端传来的 data URL。
    统一在这里限制格式和大小，避免脏图片直接进入后续识别流程。
    """
    match = re.fullmatch(r"data:image/(jpeg|png|webp);base64,(.+)", data_url or "", re.DOTALL)
    if not match:
        raise ValueError("图片格式不受支持，请选择 JPEG、PNG 或 WEBP。")

    image_type = match.group(1).lower()
    if image_type not in ALLOWED_IMAGE_TYPES:
        raise ValueError("图片类型不受支持。")

    try:
        image_bytes = base64.b64decode(match.group(2), validate=True)
    except binascii.Error as error:
        raise ValueError("图片数据已损坏，请重新上传。") from error

    if not image_bytes:
        raise ValueError("图片内容为空，请重新选择。")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError("图片不能超过 5MB，请压缩后重试。")

    return image_bytes, image_type
