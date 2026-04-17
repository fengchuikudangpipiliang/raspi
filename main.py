from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from scripts.camera.camera import VideoCamera
from scripts.database.sqlite_db import init_db


# 项目根目录，后面拼接 templates/static 都基于它。
BASE_DIR = Path(__file__).resolve().parent
# Jinja2 模板引擎，负责把 html 模板和传入的数据渲染成页面。
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# 创建 FastAPI 应用，并把静态资源目录挂到 /static。
app = FastAPI(title="face3")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
camera = VideoCamera()


# 终端识别页的演示数据。
# 现在先写死在后端里，后面再替换成真实数据库或识别结果。
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

# 管理后台页的演示数据。
# 目前只用于页面原型展示，不代表真实数据库内容。
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
    # 服务启动时先确保 SQLite 表结构已经创建好。
    init_db()
    camera.start()


@app.on_event("shutdown")
def shutdown() -> None:
    # 服务退出时释放摄像头资源，避免下次启动占用失败。
    camera.stop()


@app.get("/", response_class=HTMLResponse)
def user_screen(request: Request):
    # 渲染给待识别用户看的终端页面。
    # request 是 Jinja2 模板必须拿到的上下文对象。
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
    # 通过 MJPEG 流把摄像头画面持续推给浏览器。
    return StreamingResponse(
        camera.frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    # 渲染管理员后台页面。
    return templates.TemplateResponse(
        "admin_dashboard.html",
        {
            "request": request,
            "page_title": "后台管理",
            "data": ADMIN_DASHBOARD_DATA,
        },
    )
