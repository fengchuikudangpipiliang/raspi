from pathlib import Path
from time import perf_counter
from time import time

from fastapi import FastAPI
from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from scripts.camera.camera import VideoCamera
from scripts.admin_api import build_admin_api_router
from scripts.config.config import cfg
from scripts.database.sqlite_db import init_db
from scripts.web.liveness import LivenessChallengeService
from scripts.web.portal_submission_service import PortalAccountService
from scripts.web.roster_import_service import RosterImportService


# 项目根目录，模板和静态资源都基于它定位。
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
funnel_templates = Jinja2Templates(directory=str(BASE_DIR / "scripts" / "web" / "templates"))

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
portal_service = PortalAccountService()
roster_import_service = RosterImportService()
portal_liveness_service = LivenessChallengeService()
app.include_router(build_admin_api_router(camera=camera, started_at=APP_STARTED_AT))


# 终端识别页演示数据。
USER_SCREEN_DATA = {
    "site_name": "教学楼 A 栋",
    "welcome_title": "请面对摄像头完成签到",
    "welcome_text": "将面部保持在取景框中央，摘下口罩与帽子，系统会在识别稳定后自动记录考勤。",
    "status_label": "待识别",
    "status_text": "正在等待清晰人脸进入识别区域",
    "tips": [
        "保持正脸，距离摄像头约 40-70 厘米",
        "请勿多人同时进入识别区",
        "识别成功后将自动显示签到结果",
    ],
    "today_summary": {
        "checked_in": 128,
        "pending": 17,
        "late": 6,
    },
    "announcements": [
        "上午签到时段：07:30 - 09:00",
        "识别失败请前往管理员处人工登记",
        "请勿遮挡摄像头与补光灯",
    ],
}

# 管理后台演示数据。
ADMIN_DASHBOARD_DATA = {
    "overview": [
        {"label": "在册用户", "value": "186", "delta": "+12 本周新增"},
        {"label": "今日已签到", "value": "128", "delta": "到勤率 84.8%"},
        {"label": "迟到人数", "value": "6", "delta": "较昨日 -2"},
        {"label": "待处理异常", "value": "4", "delta": "2 条需复核"},
    ],
    "user_levels": [
        {"name": "学生", "count": 152, "color": "primary"},
        {"name": "教师", "count": 24, "color": "success"},
        {"name": "管理员", "count": 6, "color": "warning"},
        {"name": "访客", "count": 4, "color": "info"},
    ],
    "today_attendance": [
        {"time": "07:42", "name": "张三", "code": "S001", "result": "签到成功", "badge": "success"},
        {"time": "07:48", "name": "李老师", "code": "T008", "result": "签到成功", "badge": "success"},
        {"time": "08:03", "name": "王五", "code": "S016", "result": "迟到", "badge": "warning"},
        {"time": "08:11", "name": "访客-01", "code": "V003", "result": "待人工确认", "badge": "secondary"},
        {"time": "08:16", "name": "赵六", "code": "S021", "result": "识别失败", "badge": "danger"},
    ],
    "devices": [
        {"name": "1F 东门终端", "status": "在线", "detail": "信号稳定 / CPU 43%"},
        {"name": "2F 教师办公区", "status": "在线", "detail": "补光正常 / 延迟 42ms"},
        {"name": "3F 实验室入口", "status": "告警", "detail": "摄像头画面偏暗"},
    ],
    "alerts": [
        "08:16 发生 1 次连续识别失败，需要管理员检查现场光照。",
        "访客身份待确认 2 人，建议在上午 10:00 前完成审核。",
        "昨日晚间自动备份已完成，数据库状态正常。",
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
            "data": USER_SCREEN_DATA,
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


@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    """
    管理后台原型页。
    """
    return templates.TemplateResponse(
        "admin_dashboard.html",
        {
            "request": request,
            "page_title": "后台管理",
            "data": ADMIN_DASHBOARD_DATA,
        },
    )


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
