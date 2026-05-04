from datetime import datetime
from pathlib import Path
from time import perf_counter
from time import time

from fastapi import FastAPI
from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from fastapi.responses import PlainTextResponse
from fastapi.responses import RedirectResponse
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from scripts.camera.camera import VideoCamera
from scripts.admin_api import build_admin_api_router
from scripts.config.config import cfg
from scripts.database.sqlite_db import AttendanceRepository
from scripts.database.sqlite_db import init_db
from scripts.web.liveness import LivenessChallengeService
from scripts.web.portal_submission_service import PortalAccountService
from scripts.web.roster_import_service import RosterImportService


# 项目根目录，模板和静态资源都基于它定位。
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
funnel_templates = Jinja2Templates(
    directory=[
        str(BASE_DIR / "scripts" / "web" / "templates"),
        str(BASE_DIR / "templates"),
    ]
)
LOCAL_TERMINAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
LOCAL_TERMINAL_PATHS = {
    "/",
    "/video_feed",
    "/healthz",
    "/api/terminal/status",
    "/api/terminal/screen-data",
}
PORTAL_PATH_PREFIXES = ("/portal", "/api/portal", "/api/liveness", "/api/submissions")
ALWAYS_ALLOWED_PREFIXES = ("/static", "/api/admin")

# 创建主应用。
APP_STARTED_AT = time()
app = FastAPI(title="face3")
app.add_middleware(
    SessionMiddleware,
    secret_key=cfg.session_secret_key,
    session_cookie=cfg.session_cookie_name,
    same_site="lax",
    https_only=False,
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# 运行期基础服务统一放在入口层初始化，避免每个路由里重复创建。
camera = VideoCamera()
terminal_attendance_repo = AttendanceRepository()
roster_import_service = RosterImportService()
portal_service = PortalAccountService(roster_import_service=roster_import_service)
portal_liveness_service = LivenessChallengeService()
app.include_router(
    build_admin_api_router(
        camera=camera,
        started_at=APP_STARTED_AT,
        roster_import_service=roster_import_service,
    )
)



def get_terminal_recognition_backend_label() -> str:
    """
    读取终端当前实际启用的人脸识别后端。
    这个值只用于本地终端展示，不影响识别逻辑。
    """
    recognizer = getattr(camera, "recognizer", None)
    backend = getattr(recognizer, "active_recognition_model", "") if recognizer else ""
    if backend == "opencv_sface":
        return "YuNet + SFace"
    if backend == "face_recognition":
        return "dlib"
    return "自动选择"


def build_user_screen_data() -> dict:
    """
    终端识别页数据。
    右侧概况和公告尽量来自数据库与 env.json，避免页面长期显示演示假数。
    """
    today = datetime.now().astimezone().date().isoformat()
    summary = terminal_attendance_repo.get_attendance_summary(date=today)
    backend_label = get_terminal_recognition_backend_label()
    liveness_enabled = bool(cfg.attendance_liveness_enabled)
    site_name = (cfg.device_location or cfg.device_name or "未设置").strip()

    return {
        "site_name": site_name,
        "welcome_title": "请面对摄像头完成签到",
        "welcome_text": "将面部保持在取景框中央，系统会在识别稳定后自动记录考勤。",
        "tips": [
            "保持单人入镜，多人进入画面时系统会暂停签到",
            f"当前识别后端：{backend_label}",
            "活体检测已启用" if liveness_enabled else "当前按人脸识别稳定性完成签到",
        ],
        "today_stats": [
            {
                "label": "已签到",
                "value": summary["checked_in_users"],
                "alert": False,
            },
            {
                "label": "未签到",
                "value": summary["absent_users"],
                "alert": summary["absent_users"] > 0,
            },
            {
                "label": "总人数",
                "value": summary["registered_users"],
                "alert": False,
            },
        ],
        "announcements": [
            f"签到时段：{cfg.attendance_start_time} - {cfg.attendance_end_time}",
            f"设备位置：{site_name}",
            f"签到快照保留：{cfg.attendance_snapshot_retention_days} 天",
        ],
    }


@app.on_event("startup")
def startup() -> None:
    """
    服务启动时先准备数据库并导入成员名单。
    树莓派本地摄像头改为按需启动，避免外网门户动作挑战和本地视频线程同时抢占人脸识别资源。
    """
    init_db()
    summary = roster_import_service.sync_from_file()
    print(
        "[face3] roster sync finished:",
        {
            "total_rows": summary.total_rows,
            "created_count": summary.created_count,
            "updated_count": summary.updated_count,
        },
    )


@app.on_event("shutdown")
def shutdown() -> None:
    """
    进程退出时释放摄像头，避免设备被占用。
    """
    camera.stop()


def get_logged_in_user(request: Request):
    """
    统一读取当前门户登录用户。
    会话缺失或账号失效时返回 None，交给路由决定是跳转还是报错。
    """
    user_id = request.session.get("portal_user_id")
    if not user_id:
        return None
    return portal_service.require_user(user_id)


def get_request_host(request: Request) -> str:
    """
    统一解析请求主机名。
    这里只关心是不是本地环回访问，不把端口差异带进访问策略判断。
    """
    raw_host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    host = raw_host.split(",", 1)[0].strip()
    if host.startswith("[") and "]" in host:
        return host[1:host.index("]")]
    return host.split(":", 1)[0].strip().lower()


def is_portal_path(path: str) -> bool:
    """
    判断路径是否属于外网用户门户。
    这些页面和接口允许远端成员访问，但不在树莓派本地终端浏览器里暴露。
    """
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in PORTAL_PATH_PREFIXES)


def build_blocked_route_response(path: str):
    """
    被入口访问策略拦截时统一返回 404。
    这样现场用户和公网用户都不会看到不该暴露的历史页面或内部入口。
    """
    if path.startswith("/api/"):
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    return PlainTextResponse("Not Found", status_code=404)


@app.middleware("http")
async def restrict_page_entrypoints(request: Request, call_next):
    """
    统一控制页面入口：
    - 本地 127.0.0.1 / localhost 只开放终端页 `/` 及其依赖接口
    - 非本地访问只开放 `/portal/*` 这组用户门户页面和相关接口
    - `/api/admin/*` 保留给 Windows 管理端调用
    - 历史遗留的 `/admin` 页面直接下线
    """
    path = request.url.path
    if any(path == prefix or path.startswith(f"{prefix}/") for prefix in ALWAYS_ALLOWED_PREFIXES):
        return await call_next(request)
    if path == "/admin" or path.startswith("/admin/"):
        return build_blocked_route_response(path)

    host = get_request_host(request)
    if host in LOCAL_TERMINAL_HOSTS:
        if path in LOCAL_TERMINAL_PATHS:
            return await call_next(request)
        return build_blocked_route_response(path)

    if path == "/":
        return RedirectResponse(url="/portal/login", status_code=307)
    if is_portal_path(path):
        return await call_next(request)
    return build_blocked_route_response(path)


@app.get("/", response_class=HTMLResponse)
def user_screen(request: Request):
    """
    树莓派本地终端页。
    这个页面和外网注册登录门户分开，避免把终端识别流和用户账号流程混在一起。
    """
    return templates.TemplateResponse(
        "user_screen.html",
        {
            "request": request,
            "page_title": "识别签到",
            "data": build_user_screen_data(),
        },
    )


@app.get("/video_feed")
def video_feed():
    """
    通过 MJPEG 持续推送树莓派摄像头画面。
    """
    camera.start()
    return StreamingResponse(
        camera.frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/healthz")
def healthz():
    """
    终端页前端用的轻量心跳接口。
    """
    return {"status": "ok", "camera_running": camera.running}


@app.get("/api/terminal/status")
def terminal_status():
    """
    终端页左上角小进度提示接口。
    只返回轻量状态，避免给视频流增加额外负担。
    """

    return {
        "ok": True,
        "camera_running": camera.running,
        "progress": camera.get_terminal_progress(),
    }


@app.get("/api/terminal/screen-data")
def terminal_screen_data():
    """
    终端页右侧信息接口。
    数据来自本地数据库和 env.json，前端低频轮询即可。
    """

    return {
        "ok": True,
        "data": build_user_screen_data(),
    }


@app.get("/portal")
def portal_index(request: Request):
    """
    外网用户门户入口。
    已登录则进个人主页，未登录则进入登录页。
    """
    current_user = get_logged_in_user(request)
    target = "/portal/home" if current_user else "/portal/login"
    return RedirectResponse(url=target, status_code=303)


@app.get("/portal/register", response_class=HTMLResponse)
def portal_register_page(request: Request):
    """
    首次注册页面。
    用户使用管理员预置的初始密码完成首次注册，并在此时设置正式密码。
    """
    current_user = get_logged_in_user(request)
    if current_user:
        return RedirectResponse(url="/portal/home", status_code=303)

    return templates.TemplateResponse(
        "portal_register.html",
        {
            "request": request,
            "page_title": "首次注册",
        },
    )


@app.get("/portal/login", response_class=HTMLResponse)
def portal_login_page(request: Request):
    """
    登录页。
    首次注册完成后，后续都只认新密码。
    """
    current_user = get_logged_in_user(request)
    if current_user:
        return RedirectResponse(url="/portal/home", status_code=303)

    return templates.TemplateResponse(
        "portal_login.html",
        {
            "request": request,
            "page_title": "用户登录",
        },
    )


@app.get("/portal/home", response_class=HTMLResponse)
def portal_home_page(request: Request):
    """
    登录后的用户主页。
    这里展示当前账号状态和人脸资料准备情况。
    """
    current_user = get_logged_in_user(request)
    if not current_user:
        return RedirectResponse(url="/portal/login", status_code=303)

    return templates.TemplateResponse(
        "portal_home.html",
        {
            "request": request,
            "page_title": "用户中心",
            "user": current_user,
        },
    )


@app.get("/portal/face-profiles/{face_profile_id}/image")
def portal_face_profile_image(face_profile_id: int, request: Request):
    """
    登录用户查看自己已上传的人脸照片。
    这里只允许访问当前账号自己的照片文件，避免把 data 目录直接暴露成静态目录。
    """
    current_user = get_logged_in_user(request)
    if not current_user:
        return RedirectResponse(url="/portal/login", status_code=303)

    face_profile = portal_service.repo.get_face_profile_by_id(face_profile_id)
    if not face_profile or face_profile["user_id"] != current_user["id"]:
        return PlainTextResponse("Not Found", status_code=404)

    image_path = Path(face_profile["image_path"])
    if not image_path.is_absolute():
        image_path = BASE_DIR / image_path
    if not image_path.exists() or not image_path.is_file():
        return PlainTextResponse("Not Found", status_code=404)

    media_type = "image/jpeg"
    suffix = image_path.suffix.lower()
    if suffix == ".png":
        media_type = "image/png"
    elif suffix == ".webp":
        media_type = "image/webp"
    return FileResponse(str(image_path), media_type=media_type)


@app.get("/portal/face", response_class=HTMLResponse)
def portal_face_page(request: Request):
    """
    人脸资料上传页。
    外网用户登录后可访问，用于提交正式的人脸注册照。
    """
    current_user = get_logged_in_user(request)
    if not current_user:
        return RedirectResponse(url="/portal/login", status_code=303)

    return funnel_templates.TemplateResponse(
        "funnel_test.html",
        {
            "request": request,
            "page_title": "Face3 用户资料提交",
            "user": current_user,
            "portal_home_url": "/portal/home",
            "portal_logout_url": "/api/portal/logout",
            "portal_login_url": "/portal/login",
        },
    )


@app.post("/api/portal/register")
async def portal_register(request: Request):
    """
    处理首次注册。
    注册成功后直接写入登录态，减少用户再登录一次的摩擦。
    """
    try:
        payload = portal_service.decode_register_payload(await request.json())
        user = portal_service.register_member(**payload)
        request.session["portal_user_id"] = user["id"]
        return JSONResponse(
            {
                "ok": True,
                "message": "首次注册成功，请继续上传人脸资料。",
                "redirect_url": "/portal/face",
            }
        )
    except ValueError as error:
        return JSONResponse({"ok": False, "message": str(error)}, status_code=400)
    except Exception:
        return JSONResponse(
            {"ok": False, "message": "注册服务暂时不可用，请稍后重试。"},
            status_code=500,
        )


@app.post("/api/portal/login")
async def portal_login(request: Request):
    """
    登录正式账号。
    """
    try:
        payload = portal_service.decode_login_payload(await request.json())
        user = portal_service.login_user(**payload)
        request.session["portal_user_id"] = user["id"]
        return JSONResponse(
            {
                "ok": True,
                "message": "登录成功。",
                "redirect_url": "/portal/home",
            }
        )
    except ValueError as error:
        return JSONResponse({"ok": False, "message": str(error)}, status_code=400)
    except Exception:
        return JSONResponse(
            {"ok": False, "message": "登录服务暂时不可用，请稍后重试。"},
            status_code=500,
        )


@app.post("/api/portal/logout")
def portal_logout(request: Request):
    """
    主动退出登录。
    """
    request.session.pop("portal_user_id", None)
    return JSONResponse(
        {
            "ok": True,
            "message": "已退出登录。",
            "redirect_url": "/portal/login",
        }
    )


@app.post("/api/portal/face-profiles")
async def portal_face_profiles(request: Request):
    """
    登录用户上传注册照并写入 face_profiles。
    """
    current_user = get_logged_in_user(request)
    if not current_user:
        return JSONResponse(
            {"ok": False, "message": "登录状态已失效，请重新登录。"},
            status_code=401,
        )

    try:
        payload = portal_service.decode_face_payload(await request.json())
        result = portal_service.submit_face_profile(current_user["id"], payload["image_data"])
        status_code = 200 if result["ok"] else 400
        return JSONResponse(result, status_code=status_code)
    except ValueError as error:
        return JSONResponse({"ok": False, "message": str(error)}, status_code=400)
    except Exception:
        return JSONResponse(
            {"ok": False, "message": "人脸上传服务暂时不可用，请稍后重试。"},
            status_code=500,
        )


@app.post("/api/liveness/challenges")
async def create_liveness_challenge_for_portal(request: Request):
    """
    给当前登录用户创建一次动作挑战。
    主应用直接复用 Funnel 页原有的接口路径，避免再改前端活体逻辑。
    """
    current_user = get_logged_in_user(request)
    if not current_user:
        return JSONResponse(
            {"ok": False, "message": "登录状态已失效，请重新登录。"},
            status_code=401,
        )

    result = portal_liveness_service.create_challenge()
    return JSONResponse({"ok": True, **portal_liveness_service.result_to_dict(result)})


@app.post("/api/liveness/challenges/{challenge_id}/captures")
async def analyze_liveness_capture_for_portal(challenge_id: str, request: Request):
    """
    接收当前步骤抓拍图并推进动作挑战状态机。
    """
    current_user = get_logged_in_user(request)
    if not current_user:
        return JSONResponse(
            {"ok": False, "message": "登录状态已失效，请重新登录。"},
            status_code=401,
        )

    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("抓拍数据格式错误。")

        image_data = payload.get("image_data", "")
        if not image_data:
            raise ValueError("缺少抓拍图片数据。")

        from scripts.web.portal_submission_service import decode_image_data

        image_bytes, image_type = decode_image_data(image_data)
        started_at = perf_counter()
        print(
            "[face3] liveness capture start",
            {
                "challenge_id": challenge_id,
                "user_id": current_user["id"],
                "image_bytes": len(image_bytes),
            },
        )
        result = await run_in_threadpool(
            portal_liveness_service.analyze_capture,
            challenge_id,
            image_bytes,
            image_type,
        )
        print(
            "[face3] liveness capture end",
            {
                "challenge_id": challenge_id,
                "user_id": current_user["id"],
                "code": result.code,
                "state": result.state,
                "elapsed_ms": round((perf_counter() - started_at) * 1000, 1),
            },
        )
        status_code = 200 if result.code not in {"challenge_missing", "challenge_expired", "challenge_consumed"} else 400
        return JSONResponse(
            {"ok": status_code == 200, **portal_liveness_service.result_to_dict(result)},
            status_code=status_code,
        )
    except ValueError as error:
        return JSONResponse({"ok": False, "message": str(error)}, status_code=400)
    except Exception as error:
        print(
            "[face3] liveness capture crash",
            {
                "challenge_id": challenge_id,
                "user_id": current_user["id"],
                "error": repr(error),
            },
        )
        return JSONResponse(
            {"ok": False, "message": "动作挑战暂时不可用，请稍后重试。"},
            status_code=500,
        )


@app.post("/api/submissions")
async def submit_trusted_capture_for_portal(request: Request):
    """
    把通过动作挑战冻结的可信注册照写入当前登录用户的人脸档案。
    当前登录用户身份以后端会话为准，不再依赖前端重复提交身份字段。
    """
    current_user = get_logged_in_user(request)
    if not current_user:
        return JSONResponse(
            {"ok": False, "message": "登录状态已失效，请重新登录。"},
            status_code=401,
        )

    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("提交数据格式错误。")

        if payload.get("source_mode") != "camera":
            raise ValueError("当前入口仅支持摄像头现场采集。")
        if not payload.get("consent"):
            raise ValueError("请先勾选授权说明后再提交。")

        challenge_id = (payload.get("challenge_id", "") or "").strip()
        if not challenge_id:
            raise ValueError("请先完成动作活体挑战。")

        trusted_capture = portal_liveness_service.get_trusted_capture(challenge_id)
        started_at = perf_counter()
        print(
            "[face3] portal submission start",
            {
                "challenge_id": challenge_id,
                "user_id": current_user["id"],
                "image_bytes": len(trusted_capture.image_bytes),
            },
        )
        result = await run_in_threadpool(
            portal_service.submit_face_profile_from_bytes,
            current_user["id"],
            trusted_capture.image_bytes,
            trusted_capture.image_type,
        )
        print(
            "[face3] portal submission end",
            {
                "challenge_id": challenge_id,
                "user_id": current_user["id"],
                "ok": result["ok"],
                "elapsed_ms": round((perf_counter() - started_at) * 1000, 1),
            },
        )
        if not result["ok"]:
            portal_liveness_service.consume_challenge(challenge_id)
            return JSONResponse(
                {
                    **result,
                    "require_new_challenge": True,
                },
                status_code=400,
            )

        portal_liveness_service.consume_challenge(challenge_id)
        return JSONResponse(
            {
                **result,
                "message": "人脸资料提交成功，已绑定到当前账号。",
            }
        )
    except ValueError as error:
        return JSONResponse({"ok": False, "message": str(error)}, status_code=400)
    except Exception as error:
        print(
            "[face3] portal submission crash",
            {
                "user_id": current_user["id"],
                "error": repr(error),
            },
        )
        return JSONResponse(
            {"ok": False, "message": "人脸资料提交服务暂时不可用，请稍后重试。"},
            status_code=500,
        )
