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
from fastapi.templating import Jinja2Templates


# 这个独立应用专门服务公网人脸资料提交，不依赖主项目的摄像头线程和数据库。
BASE_DIR = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
DATA_DIR = BASE_DIR / "data" / "funnel_registrations"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 前端模板目录。
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# 允许的图片类型和最大字节数。
ALLOWED_IMAGE_TYPES = {"jpeg", "png", "webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024

# 独立测试应用，后续可逐步升级成真正的公网注册入口。
app = FastAPI(title="face3-funnel-test")


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


def save_submission(payload: dict) -> dict:
    """
    保存一次用户提交。
    每次提交都会创建独立目录，目录里同时保存图片文件和 metadata.json，便于后续追踪和调试。
    """
    submission_id = datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid4().hex[:8]
    submission_dir = DATA_DIR / submission_id
    submission_dir.mkdir(parents=True, exist_ok=False)

    image_bytes, image_type = decode_image_data(payload["image_data"])
    image_path = submission_dir / f"face.{image_type}"
    image_path.write_bytes(image_bytes)

    metadata = {
        "submission_id": submission_id,
        "full_name": sanitize_text(payload.get("full_name", ""), 40),
        "student_or_employee_id": sanitize_text(payload.get("student_or_employee_id", ""), 40),
        "phone": sanitize_text(payload.get("phone", ""), 20),
        "source_mode": payload.get("source_mode", ""),
        "notes": sanitize_text(payload.get("notes", ""), 200),
        "consent": bool(payload.get("consent")),
        "image_path": str(image_path.relative_to(BASE_DIR)),
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
    这里把和业务最相关的边界情况全部拦下来，避免出现“没勾同意”“没照片”“来源模式错乱”等无效数据。
    """
    full_name = sanitize_text(payload.get("full_name", ""), 40)
    if len(full_name) < 2:
        raise ValueError("姓名至少需要 2 个字符。")

    person_id = sanitize_text(payload.get("student_or_employee_id", ""), 40)
    if not person_id:
        raise ValueError("请填写学号或工号。")

    source_mode = payload.get("source_mode")
    if source_mode not in {"upload", "camera"}:
        raise ValueError("照片来源无效，请重新选择。")

    image_data = payload.get("image_data", "")
    if not image_data:
        raise ValueError("请先上传照片或拍摄照片。")

    if not payload.get("consent"):
        raise ValueError("请先勾选授权说明后再提交。")

    payload["full_name"] = full_name
    payload["student_or_employee_id"] = person_id
    payload["phone"] = sanitize_text(payload.get("phone", ""), 20)
    payload["notes"] = sanitize_text(payload.get("notes", ""), 200)
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
        metadata = save_submission(payload)
        return JSONResponse(
            {
                "ok": True,
                "message": "资料已提交成功，请等待管理员审核。",
                "submission_id": metadata["submission_id"],
            }
        )
    except ValueError as error:
        return JSONResponse({"ok": False, "message": str(error)}, status_code=400)
    except Exception:
        return JSONResponse(
            {"ok": False, "message": "服务暂时不可用，请稍后重试。"},
            status_code=500,
        )
