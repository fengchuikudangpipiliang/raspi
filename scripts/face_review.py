import json
from typing import Iterable


FACE_REJECTION_REASON_LABELS = {
    "cartoon_avatar": "卡通头像或虚拟形象",
    "screen_photo": "翻拍屏幕或电子设备照片",
    "printed_photo": "纸质照片或非真人现场",
    "face_not_clear": "人脸不清晰",
    "bad_lighting": "光线过强或过暗",
    "pose_invalid": "不是正脸或角度过大",
    "occluded_face": "口罩、帽子或遮挡过多",
    "multiple_faces": "画面中存在多人",
    "info_mismatch": "身份信息与照片不符",
    "other": "其他原因",
}


def normalize_review_reason_codes(raw_codes) -> list[str]:
    """
    统一清洗驳回原因编码列表。
    允许输入 list / tuple / set，也允许直接传 JSON 字符串，最终只保留合法、去重后的编码。
    """

    if raw_codes is None:
        return []

    values: Iterable
    if isinstance(raw_codes, str):
        text = raw_codes.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            values = [text]
        else:
            values = parsed if isinstance(parsed, list) else [parsed]
    elif isinstance(raw_codes, (list, tuple, set)):
        values = raw_codes
    else:
        values = [raw_codes]

    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        code = str(item or "").strip().lower()
        if not code or code not in FACE_REJECTION_REASON_LABELS or code in seen:
            continue
        seen.add(code)
        normalized.append(code)
    return normalized


def serialize_review_reason_codes(reason_codes: list[str]) -> str:
    """
    把驳回原因编码列表转成数据库里统一存储的 JSON 文本。
    """

    return json.dumps(normalize_review_reason_codes(reason_codes), ensure_ascii=False)


def build_review_reason_labels(reason_codes) -> list[str]:
    """
    给前端和 API 返回中文标签数组，避免调用方重复维护映射。
    """

    return [FACE_REJECTION_REASON_LABELS[code] for code in normalize_review_reason_codes(reason_codes)]
