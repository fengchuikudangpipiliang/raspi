from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import FileResponse

from scripts.config.config import cfg
from scripts.database.sqlite_db import AttendanceRepository
from scripts.device_status_service import DeviceStatusService
from scripts.face_review import FACE_REJECTION_REASON_LABELS
from scripts.face_review import build_review_reason_labels
from scripts.face_review import normalize_review_reason_codes
from scripts.web.account_security import hash_secret
from scripts.web.account_security import normalize_name
from scripts.web.account_security import validate_new_password
from scripts.web.roster_import_service import RosterImportService


def build_admin_api_router(camera, started_at, roster_import_service=None) -> APIRouter:
    """
    构建设备侧管理员 API 路由。
    这些接口给 Windows 管理项目通过 Tailscale 直接调用，不依赖浏览器 Session。
    """

    router = APIRouter(prefix="/api/admin", tags=["admin-api"])
    repo = AttendanceRepository()
    roster_import_service = roster_import_service or RosterImportService(repo=repo)
    device_status_service = DeviceStatusService(camera=camera, repo=repo, started_at=started_at)
    project_root = Path(__file__).resolve().parents[1]

    def require_admin_token(request: Request) -> None:
        configured_token = (cfg.admin_api_token or "").strip()
        if not configured_token:
            raise HTTPException(status_code=503, detail="管理员 API Token 尚未配置。")

        authorization = request.headers.get("Authorization", "").strip()
        fallback_token = request.headers.get("X-Admin-Token", "").strip()
        if authorization.lower().startswith("bearer "):
            provided_token = authorization[7:].strip()
        else:
            provided_token = fallback_token

        if not provided_token or provided_token != configured_token:
            raise HTTPException(status_code=401, detail="管理员 API 鉴权失败。")

    def resolve_local_file(path_text: str) -> Path:
        if not path_text:
            raise HTTPException(status_code=404, detail="文件路径不存在。")
        path = Path(path_text)
        if not path.is_absolute():
            path = (project_root / path).resolve()
        else:
            path = path.resolve()

        try:
            path.relative_to(project_root)
        except ValueError as error:
            raise HTTPException(status_code=400, detail="文件路径非法。") from error

        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="文件不存在。")
        return path

    def serialize_user_summary(user: dict) -> dict:
        approved_count = int(user.get("approved_face_profiles_count") or 0)
        pending_count = int(user.get("pending_face_profiles_count") or 0)
        rejected_count = int(user.get("rejected_face_profiles_count") or 0)
        return {
            "id": user["id"],
            "roster_member_id": user.get("roster_member_id"),
            "name": user["name"],
            "code": user["code"],
            "role": user.get("roster_role") or "member",
            "status": user.get("roster_status") or "active",
            "registered": bool(user.get("password_hash")),
            "password_changed_at": user.get("password_changed_at"),
            "last_login_at": user.get("last_login_at"),
            "created_at": user.get("created_at"),
            "face_profiles_count": int(user.get("face_profiles_count") or 0),
            "approved_face_profiles_count": approved_count,
            "pending_face_profiles_count": pending_count,
            "rejected_face_profiles_count": rejected_count,
            "face_profile_ready": int(user.get("face_profiles_count") or 0) > 0,
            "face_profile_recognition_ready": approved_count > 0,
        }

    def build_registered_codes() -> set[str]:
        return {
            user["code"]
            for user in repo.list_users_with_face_stats(registered_only=True)
        }

    def serialize_roster_member(member: dict, registered_codes: set[str]) -> dict:
        return {
            **member,
            "registered": member["code"] in registered_codes,
        }

    async def decode_roster_member_payload(request: Request) -> dict:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="提交数据格式错误。")
        return payload

    def ensure_roster_synced() -> None:
        try:
            roster_import_service.sync_from_file_if_changed()
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    def serialize_face_profile(face_profile: dict) -> dict:
        review_status = (face_profile.get("review_status") or "pending").strip().lower()
        review_reason_codes = normalize_review_reason_codes(face_profile.get("review_reason_codes"))
        return {
            "id": face_profile["id"],
            "user_id": face_profile["user_id"],
            "name": face_profile["name"],
            "code": face_profile["code"],
            "image_path": face_profile["image_path"],
            "review_status": review_status,
            "review_reason_codes": review_reason_codes,
            "review_reason_labels": build_review_reason_labels(review_reason_codes),
            "review_comment": face_profile.get("review_comment"),
            "reviewed_at": face_profile.get("reviewed_at"),
            "reviewed_by": face_profile.get("reviewed_by"),
            "recognition_enabled": review_status == "approved",
            "created_at": face_profile["created_at"],
            "image_url": f"/api/admin/face-profiles/{face_profile['id']}/image",
        }

    def serialize_face_rejection_history(item: dict) -> dict:
        review_reason_codes = normalize_review_reason_codes(item.get("review_reason_codes"))
        return {
            "id": item["id"],
            "user_id": item["user_id"],
            "face_profile_id": item.get("face_profile_id"),
            "review_reason_codes": review_reason_codes,
            "review_reason_labels": build_review_reason_labels(review_reason_codes),
            "review_comment": item.get("review_comment"),
            "reviewed_by": item.get("reviewed_by"),
            "created_at": item.get("created_at"),
        }

    def attendance_snapshot_exists(record: dict) -> bool:
        if not record.get("snapshot_path"):
            return False
        try:
            return resolve_local_file(record["snapshot_path"]).is_file()
        except HTTPException:
            return False

    def cleanup_local_files(path_texts: list[str]) -> dict:
        """
        删除数据库记录关联的项目内本地文件。
        文件清理采用最佳努力策略：非法路径、缺失文件或删除失败会记录到 skipped_files，不影响数据库删除结果。
        """
        deleted_files = []
        skipped_files = []
        seen_paths = set()

        for path_text in path_texts:
            if not path_text or path_text in seen_paths:
                continue
            seen_paths.add(path_text)

            try:
                file_path = resolve_local_file(path_text)
            except HTTPException as error:
                skipped_files.append({"path": path_text, "reason": str(error.detail)})
                continue

            try:
                file_path.unlink(missing_ok=True)
                deleted_files.append(str(file_path.relative_to(project_root)))
            except OSError as error:
                skipped_files.append({"path": path_text, "reason": str(error)})

        return {
            "deleted_files": deleted_files,
            "skipped_files": skipped_files,
        }

    def serialize_attendance_record(record: dict) -> dict:
        snapshot_available = attendance_snapshot_exists(record)
        return {
            "id": record["id"],
            "user_id": record["user_id"],
            "name": record["name"],
            "code": record["code"],
            "check_type": record["check_type"],
            "check_time": record["check_time"],
            "snapshot_path": record["snapshot_path"],
            "snapshot_available": snapshot_available,
            "snapshot_url": f"/api/admin/attendance/{record['id']}/snapshot" if snapshot_available else None,
            "confidence": record["confidence"],
        }

    @router.get("/device/info")
    def get_device_info(request: Request):
        require_admin_token(request)
        return {"ok": True, "data": device_status_service.build_device_info()}

    @router.get("/device/health")
    def get_device_health(request: Request):
        require_admin_token(request)
        return {"ok": True, "data": device_status_service.build_health()}

    @router.get("/device/metrics")
    def get_device_metrics(request: Request):
        require_admin_token(request)
        return {"ok": True, "data": device_status_service.build_metrics()}

    @router.post("/device/reload-config")
    def reload_device_config(request: Request):
        require_admin_token(request)
        changed = cfg.reload()
        return {
            "ok": True,
            "data": {
                "changed": bool(changed),
                "device_id": cfg.device_id,
                "device_name": cfg.device_name,
                "device_location": cfg.device_location,
            },
        }

    @router.post("/roster-members/sync")
    def sync_roster_members(request: Request):
        require_admin_token(request)
        try:
            result = roster_import_service.sync_from_file()
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {
            "ok": True,
            "data": {
                "synced": True,
                "roster_path": str(roster_import_service.roster_path),
                "total_rows": result.total_rows,
                "created_count": result.created_count,
                "updated_count": result.updated_count,
            },
        }

    @router.get("/roster-members")
    def get_roster_members(request: Request, search: str = "", status: str = ""):
        require_admin_token(request)
        ensure_roster_synced()
        registered_codes = build_registered_codes()
        status = (status or "").strip().lower()
        search = (search or "").strip()
        items = []
        for member in repo.list_roster_members():
            if search and search not in member["name"] and search.upper() not in member["code"]:
                continue
            if status and member["status"] != status:
                continue
            items.append(serialize_roster_member(member, registered_codes))
        return {"ok": True, "items": items, "total": len(items)}

    @router.post("/roster-members")
    async def create_roster_member(request: Request):
        require_admin_token(request)
        payload = await decode_roster_member_payload(request)
        try:
            result = roster_import_service.create_member(
                name=payload.get("name", ""),
                code=payload.get("code", ""),
                role=payload.get("role", ""),
                status=payload.get("status", ""),
                initial_password=payload.get("initial_password", ""),
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        registered_codes = build_registered_codes()
        return {
            "ok": True,
            "data": {
                "action": result["action"],
                "member": serialize_roster_member(result["member"], registered_codes),
            },
        }

    @router.put("/roster-members/{roster_member_id}")
    async def update_roster_member(request: Request, roster_member_id: int):
        require_admin_token(request)
        payload = await decode_roster_member_payload(request)
        try:
            result = roster_import_service.update_member(
                roster_member_id,
                name=payload.get("name", ""),
                role=payload.get("role", ""),
                status=payload.get("status", ""),
                initial_password=payload.get("initial_password", ""),
                code=payload.get("code", ""),
            )
        except ValueError as error:
            message = str(error)
            status_code = 404 if message == "成员名单不存在。" else 400
            raise HTTPException(status_code=status_code, detail=message) from error

        registered_codes = build_registered_codes()
        return {
            "ok": True,
            "data": {
                "action": result["action"],
                "member": serialize_roster_member(result["member"], registered_codes),
            },
        }

    @router.delete("/roster-members/{roster_member_id}")
    def delete_roster_member(request: Request, roster_member_id: int):
        """
        删除未激活的初始成员名单。
        已关联用户的成员不允许直接删除，避免 roster_members 与 users 的业务链路被意外切断。
        """
        require_admin_token(request)
        try:
            result = roster_import_service.delete_member(roster_member_id)
        except ValueError as error:
            message = str(error)
            if message == "成员名单不存在。":
                status_code = 404
            elif "已关联激活用户" in message:
                status_code = 409
            else:
                status_code = 400
            raise HTTPException(status_code=status_code, detail=message) from error

        member = result["member"]
        return {
            "ok": True,
            "data": {
                "deleted": bool(result["deleted"]),
                "csv_removed": bool(result["csv_removed"]),
                "roster_member_id": roster_member_id,
                "name": member["name"],
                "code": member["code"],
            },
        }

    @router.get("/users")
    def get_users(request: Request, search: str = "", status: str = "", registered_only: bool = False):
        require_admin_token(request)
        ensure_roster_synced()
        items = [serialize_user_summary(item) for item in repo.list_users_with_face_stats(search=search, status=status, registered_only=registered_only)]
        return {"ok": True, "items": items, "total": len(items)}

    @router.get("/users/{user_id}")
    def get_user_detail(request: Request, user_id: int):
        require_admin_token(request)
        ensure_roster_synced()
        user = repo.get_user_detail(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在。")
        face_profiles = [serialize_face_profile(item) for item in repo.list_face_profiles_for_user(user_id)]
        recent_rejections = [
            serialize_face_rejection_history(item)
            for item in repo.list_face_rejection_history_for_user(
                user_id,
                limit=max(int(cfg.portal_face_rejection_history_limit), 1),
            )
        ]
        return {
            "ok": True,
            "data": {
                **serialize_user_summary(user),
                "face_profiles": face_profiles,
                "recent_face_rejections": recent_rejections,
            },
        }

    @router.delete("/users/{user_id}")
    def delete_user(request: Request, user_id: int):
        """
        删除已激活人员及其业务数据。
        删除用户会同步移除人脸档案、驳回历史、考勤记录，并尽量清理注册照和签到快照文件。
        """
        require_admin_token(request)
        ensure_roster_synced()
        user = repo.get_user_detail(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在。")

        file_paths = repo.list_user_file_paths(user_id)
        deleted = repo.delete_user(user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="用户不存在。")

        cleanup = cleanup_local_files(
            [
                *file_paths["face_profile_images"],
                *file_paths["attendance_snapshots"],
            ]
        )
        return {
            "ok": True,
            "data": {
                "deleted": True,
                "user_id": user_id,
                "name": user["name"],
                "code": user["code"],
                "roster_member_id": user.get("roster_member_id"),
                "roster_member_retained": bool(user.get("roster_member_id")),
                "face_profile_image_count": len(file_paths["face_profile_images"]),
                "attendance_snapshot_count": len(file_paths["attendance_snapshots"]),
                **cleanup,
            },
        }

    @router.post("/users/{user_id}/status")
    async def update_user_status(request: Request, user_id: int):
        require_admin_token(request)
        ensure_roster_synced()
        payload = await request.json()
        status = (payload.get("status", "") or "").strip().lower() if isinstance(payload, dict) else ""
        if status not in {"active", "disabled"}:
            raise HTTPException(status_code=400, detail="状态只允许 active 或 disabled。")

        user = repo.get_user_detail(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在。")
        if not user.get("roster_member_id"):
            raise HTTPException(status_code=400, detail="该用户没有绑定成员名单，无法更新状态。")
        roster_member = repo.get_roster_member_by_id(user["roster_member_id"])
        if not roster_member:
            raise HTTPException(status_code=404, detail="用户关联的成员名单不存在。")
        try:
            result = roster_import_service.update_member(
                roster_member["id"],
                name=roster_member["name"],
                role=roster_member["role"],
                status=status,
            )
        except ValueError as error:
            message = str(error)
            status_code = 404 if message == "成员名单不存在。" else 400
            raise HTTPException(status_code=status_code, detail=message) from error
        return {
            "ok": True,
            "data": {
                "updated": result["action"] in {"created", "updated"},
                "user_id": user_id,
                "status": status,
            },
        }

    @router.post("/users/{user_id}/password/reset")
    async def reset_user_password(request: Request, user_id: int):
        require_admin_token(request)
        ensure_roster_synced()
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="提交数据格式错误。")

        new_password = (payload.get("new_password", "") or "").strip()
        confirm_password = (payload.get("confirm_password", "") or new_password).strip()
        user = repo.get_user_detail(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在。")
        if not user.get("password_hash"):
            raise HTTPException(status_code=400, detail="该用户尚未完成首次注册，不能直接重置登录密码。")

        validated_password = validate_new_password(
            code=user["code"],
            name=normalize_name(user["name"]),
            initial_password="",
            new_password=new_password,
            confirm_password=confirm_password,
        )
        changed = repo.update_user_password_hash(user_id, hash_secret(validated_password))
        return {
            "ok": True,
            "data": {
                "updated": changed,
                "user_id": user_id,
            },
        }

    @router.get("/face-profiles/rejection-reasons")
    def get_face_profile_rejection_reasons(request: Request):
        """
        返回管理员审核可选的驳回原因列表。
        Windows 管理端可以直接拿这份定义渲染多选项，避免本地再维护一份枚举。
        """

        require_admin_token(request)
        items = [{"code": code, "label": label} for code, label in FACE_REJECTION_REASON_LABELS.items()]
        return {"ok": True, "items": items, "total": len(items)}

    @router.get("/face-profiles")
    def get_face_profiles(
        request: Request,
        limit: int = 100,
        user_id: Optional[int] = None,
        code: str = "",
        review_status: str = "",
    ):
        """
        列出人脸档案。
        Windows 管理端可以按审核状态筛待审核列表，再逐条进入图片预览和审核操作。
        """

        require_admin_token(request)
        safe_limit = min(max(int(limit), 1), 200)
        normalized_review_status = (review_status or "").strip().lower()
        if normalized_review_status and normalized_review_status not in {"pending", "approved", "rejected"}:
            raise HTTPException(status_code=400, detail="review_status 只允许 pending、approved 或 rejected。")
        items = [
            serialize_face_profile(item)
            for item in repo.list_face_profiles(
                limit=safe_limit,
                user_id=user_id,
                code=code,
                review_status=normalized_review_status,
            )
        ]
        return {"ok": True, "items": items, "total": len(items)}

    @router.get("/face-profiles/{face_profile_id}")
    def get_face_profile_detail(request: Request, face_profile_id: int):
        """
        获取单条人脸档案详情。
        这里返回审核状态和审核备注，方便 Windows 管理端在详情抽屉或弹窗里直接展示。
        """

        require_admin_token(request)
        face_profile = repo.get_face_profile_by_id(face_profile_id)
        if not face_profile:
            raise HTTPException(status_code=404, detail="人脸档案不存在。")
        recent_rejections = [
            serialize_face_rejection_history(item)
            for item in repo.list_face_rejection_history_for_user(
                face_profile["user_id"],
                limit=max(int(cfg.portal_face_rejection_history_limit), 1),
            )
        ]
        return {
            "ok": True,
            "data": {
                **serialize_face_profile(face_profile),
                "recent_rejections": recent_rejections,
            },
        }

    @router.get("/face-profiles/{face_profile_id}/image")
    def get_face_profile_image(request: Request, face_profile_id: int):
        require_admin_token(request)
        face_profile = repo.get_face_profile_by_id(face_profile_id)
        if not face_profile:
            raise HTTPException(status_code=404, detail="人脸档案不存在。")
        file_path = resolve_local_file(face_profile["image_path"])
        return FileResponse(file_path)

    @router.post("/face-profiles/{face_profile_id}/review")
    async def review_face_profile(request: Request, face_profile_id: int):
        """
        审核指定人脸档案。
        管理员把 `review_status` 改成 approved 或 rejected 后，树莓派终端的正式识别名单会随下一次重载同步生效。
        """

        require_admin_token(request)
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="提交数据格式错误。")

        review_status = (payload.get("review_status", "") or "").strip().lower()
        review_reason_codes = payload.get("review_reason_codes", [])
        review_comment = (payload.get("review_comment", "") or "").strip()
        reviewed_by = (payload.get("reviewed_by", "") or "").strip()

        try:
            face_profile = repo.review_face_profile(
                face_profile_id=face_profile_id,
                review_status=review_status,
                review_reason_codes=review_reason_codes,
                review_comment=review_comment,
                reviewed_by=reviewed_by,
                rejection_history_limit=max(int(cfg.portal_face_rejection_history_limit), 1),
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        if not face_profile:
            raise HTTPException(status_code=404, detail="人脸档案不存在。")

        return {
            "ok": True,
            "data": {
                **serialize_face_profile(face_profile),
                "recent_rejections": [
                    serialize_face_rejection_history(item)
                    for item in repo.list_face_rejection_history_for_user(
                        face_profile["user_id"],
                        limit=max(int(cfg.portal_face_rejection_history_limit), 1),
                    )
                ],
            },
        }

    @router.delete("/face-profiles/{face_profile_id}")
    def delete_face_profile(request: Request, face_profile_id: int):
        require_admin_token(request)
        face_profile = repo.get_face_profile_by_id(face_profile_id)
        if not face_profile:
            raise HTTPException(status_code=404, detail="人脸档案不存在。")

        file_path = None
        try:
            file_path = resolve_local_file(face_profile["image_path"])
        except HTTPException:
            file_path = None

        deleted = repo.delete_face_profile(face_profile_id)
        if file_path and file_path.exists():
            file_path.unlink(missing_ok=True)

        return {
            "ok": True,
            "data": {
                "deleted": deleted,
                "face_profile_id": face_profile_id,
            },
        }

    @router.get("/attendance")
    def get_attendance_records(request: Request, limit: int = 50, date: str = "", code: str = "", name: str = ""):
        require_admin_token(request)
        safe_limit = min(max(int(limit), 1), 300)
        items = [serialize_attendance_record(item) for item in repo.list_attendance_records(limit=safe_limit, date=date, code=code, name=name)]
        return {"ok": True, "items": items, "total": len(items)}

    @router.get("/attendance/today-summary")
    def get_attendance_today_summary(request: Request, date: str = ""):
        require_admin_token(request)
        if not date:
            date = datetime.now().astimezone().date().isoformat()
        return {"ok": True, "data": repo.get_attendance_summary(date=date)}

    @router.get("/attendance/{attendance_id}/snapshot")
    def get_attendance_snapshot(request: Request, attendance_id: int):
        require_admin_token(request)
        record = repo.get_attendance_record_by_id(attendance_id)
        if not record:
            raise HTTPException(status_code=404, detail="考勤记录不存在。")
        if not record.get("snapshot_path"):
            raise HTTPException(status_code=404, detail="该考勤记录没有快照。")
        file_path = resolve_local_file(record["snapshot_path"])
        return FileResponse(file_path)

    return router
