import base64
import binascii
import json
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from scripts.web.liveness import LivenessChallengeService
from scripts.web.registration_validation import RegistrationValidationPipeline
from scripts.web.registration_validation import results_to_dicts

# 这个独立应用专门服务公网人脸资料提交，不依赖主项目的摄像头线程和数据库。
BASE_DIR = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
DATA_DIR = BASE_DIR / "data" / "funnel_registrations"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 前端模板目录。
templates = Jinja2Templates(
    directory=[
        str(TEMPLATE_DIR),
        str(BASE_DIR / "templates"),
    ]
)

# 允许的图片类型和最大字节数。
ALLOWED_IMAGE_TYPES = {"jpeg", "png", "webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024

# 独立测试应用，后续可逐步升级成真正的公网注册入口。
app = FastAPI(title="face3-funnel-test")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
# 质量校验流水线统一在这里初始化，后续替换或扩展校验器时不需要改路由逻辑。
validation_pipeline = RegistrationValidationPipeline()
# 活体挑战服务独立管理会话和受信任截图，避免在路由层堆逻辑。
liveness_service = LivenessChallengeService()


def sanitize_text(value: str, max_length: int) -> str:
    """
    对用户输入做最小清洗。
    这里只做去首尾空格、压缩连续空白和长度截断，避免把奇怪字符原样写入磁盘元数据。
    """
    value = re.sub(r"\s+", " ", (value or "").strip())
    return value[:max_length]


def decode_image_data(data_url: str) -> tuple[bytes, str]:
    """
    把前端传来的 data URL 解码成原始图片字节。
    只允许常见图片类型，并在这里统一做大小控制，避免异常数据直接落盘。
    """
    match = re.fullmatch(r"data:image/(jpeg|png|webp);base64,(.+)", data_url or "", re.DOTALL)
    if not match:
        raise ValueError("图片格式不受支持，请重新选择 JPEG、PNG 或 WEBP 图片。")

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


def save_submission(
    payload: dict,
    image_bytes: bytes,
    image_type: str,
    validation_results: list[dict],
    liveness_payload: dict,
) -> dict:
    """
    保存一次用户提交。
    每次提交都会创建独立目录，目录里同时保存图片文件和 metadata.json，便于后续追踪和调试。
    当前注册照只来自后端冻结的可信抓拍，不再接受前端直接指定最终图片。
    """
    submission_id = datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid4().hex[:8]
    submission_dir = DATA_DIR / submission_id
    submission_dir.mkdir(parents=True, exist_ok=False)

    image_path = submission_dir / f"face.{image_type}"
    image_path.write_bytes(image_bytes)

    metadata = {
        "submission_id": submission_id,
        "full_name": sanitize_text(payload.get("full_name", ""), 40),
        "student_or_employee_id": sanitize_text(payload.get("student_or_employee_id", ""), 40),
        "phone": sanitize_text(payload.get("phone", ""), 20),
        "source_mode": payload.get("source_mode", ""),
        "notes": sanitize_text(payload.get("notes", ""), 200),
        "challenge_id": payload.get("challenge_id", ""),
        "consent": bool(payload.get("consent")),
        "image_path": str(image_path.relative_to(BASE_DIR)),
        "review_status": "pending",
        "liveness": liveness_payload,
        "validation_results": validation_results,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    (submission_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return metadata


def validate_payload(payload: dict) -> dict:
    """
    对用户提交做统一校验。
    当前公网入口只允许摄像头现场采集，这样才能和后续活体挑战形成闭环。
    这里把和业务最相关的边界情况全部拦下来，避免出现“没勾同意”“没照片”“来源模式错乱”等无效数据。
    """
    full_name = sanitize_text(payload.get("full_name", ""), 40)
    if len(full_name) < 2:
        raise ValueError("姓名至少需要 2 个字符。")

    person_id = sanitize_text(payload.get("student_or_employee_id", ""), 40)
    if not person_id:
        raise ValueError("请填写学号或工号。")

    source_mode = payload.get("source_mode")
    if source_mode != "camera":
        raise ValueError("当前注册入口仅支持摄像头现场采集。")

    challenge_id = sanitize_text(payload.get("challenge_id", ""), 64)
    if not challenge_id:
        raise ValueError("请先完成动作活体挑战。")

    if not payload.get("consent"):
        raise ValueError("请先勾选授权说明后再提交。")

    payload["full_name"] = full_name
    payload["student_or_employee_id"] = person_id
    payload["phone"] = sanitize_text(payload.get("phone", ""), 20)
    payload["notes"] = sanitize_text(payload.get("notes", ""), 200)
    payload["challenge_id"] = challenge_id
    return payload


@app.get("/", response_class=HTMLResponse)
def funnel_test_page(request: Request):
    """
    返回公网用户提交页。
    这个页面模拟真实应用中的“授权 + 人脸采集 + 提交”流程。
    """
    return templates.TemplateResponse(
        "funnel_test.html",
        {
            "request": request,
            "page_title": "Face3 用户资料提交",
            "user": None,
            "portal_home_url": None,
            "portal_logout_url": None,
            "portal_login_url": None,
        },
    )


@app.post("/api/submissions")
async def create_submission(request: Request):
    """
    接收前端 JSON 提交并保存到本地。
    返回统一 JSON，方便前端根据成功或失败结果切换提示状态。
    """
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("提交数据格式错误。")

        payload = validate_payload(payload)
        trusted_capture = liveness_service.get_trusted_capture(payload["challenge_id"])
        image_bytes = trusted_capture.image_bytes
        image_type = trusted_capture.image_type
        passed, validation_results = validation_pipeline.validate(image_bytes)
        validation_payload = results_to_dicts(validation_results)

        if not passed:
            liveness_service.consume_challenge(payload["challenge_id"])
            return JSONResponse(
                {
                    "ok": False,
                    "message": "照片未通过质量校验，请重新开始动作挑战后再提交。",
                    "require_new_challenge": True,
                    "validation_results": validation_payload,
                },
                status_code=400,
            )

        liveness_payload = {
            "challenge_id": trusted_capture.challenge_id,
            "state": trusted_capture.state,
            "capture_source": "step_action_trusted_capture",
            "steps": trusted_capture.steps_payload,
        }
        metadata = save_submission(payload, image_bytes, image_type, validation_payload, liveness_payload)
        liveness_service.consume_challenge(payload["challenge_id"])
        return JSONResponse(
            {
                "ok": True,
                "message": "资料已提交成功，当前状态为待审核。",
                "submission_id": metadata["submission_id"],
                "validation_results": validation_payload,
            }
        )
    except ValueError as error:
        return JSONResponse({"ok": False, "message": str(error)}, status_code=400)
    except Exception:
        return JSONResponse(
            {"ok": False, "message": "服务暂时不可用，请稍后重试。"},
            status_code=500,
        )


@app.post("/api/liveness/challenges")
async def create_liveness_challenge():
    """
    创建一次新的动作活体挑战。
    前端每次开始验证前都要先拿一个新的 challenge_id。
    """
    result = liveness_service.create_challenge()
    return JSONResponse({"ok": True, **liveness_service.result_to_dict(result)})


@app.post("/api/liveness/challenges/{challenge_id}/captures")
async def analyze_liveness_capture(challenge_id: str, request: Request):
    """
    接收前端当前步骤的抓拍图并推进动作挑战状态机。
    这里不负责最终注册提交，只负责动作挑战本身。
    """
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("抓拍数据格式错误。")

        image_data = payload.get("image_data", "")
        if not image_data:
            raise ValueError("缺少抓拍图片数据。")

        image_bytes, image_type = decode_image_data(image_data)
        result = liveness_service.analyze_capture(challenge_id, image_bytes, image_type)
        status_code = 200 if result.code not in {"challenge_missing", "challenge_expired", "challenge_consumed"} else 400
        return JSONResponse({"ok": status_code == 200, **liveness_service.result_to_dict(result)}, status_code=status_code)
    except ValueError as error:
        return JSONResponse({"ok": False, "message": str(error)}, status_code=400)
    except Exception:
        return JSONResponse(
            {"ok": False, "message": "动作挑战暂时不可用，请稍后重试。"},
            status_code=500,
        )
