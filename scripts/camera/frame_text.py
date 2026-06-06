from functools import lru_cache
from pathlib import Path
from typing import Iterable
from typing import Optional

import cv2
import numpy as np
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont

from scripts.config.config import cfg


PROJECT_ROOT = Path(__file__).resolve().parents[2]

FONT_CANDIDATES = (
    "static/vendor/fonts/noto-sans-sc-600.ttf",
    "static/vendor/fonts/noto-sans-sc-500.ttf",
    "static/vendor/fonts/noto-sans-sc-400.ttf",
    "static/fonts/NotoSansCJK-Regular.ttc",
    "static/fonts/NotoSansSC-Regular.otf",
    "static/fonts/SourceHanSansSC-Regular.otf",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
)


def _resolve_path(path_text: str) -> Path:
    """
    把字体候选路径统一解析成绝对路径。
    相对路径始终按项目根目录解析，避免服务从不同工作目录启动时找不到项目内字体。
    """
    path = Path(path_text)
    if path.is_absolute():
        return path
    return (PROJECT_ROOT / path).resolve()


def _bgr_to_rgb(color: tuple[int, int, int]) -> tuple[int, int, int]:
    return (int(color[2]), int(color[1]), int(color[0]))


def resolve_font_path() -> Optional[str]:
    """
    解析可用于摄像头叠字的中文字体路径。

    优先级：
    1. `env.json` 显式配置的 `camera_overlay_font_path`
    2. 项目内预留的字体文件
    3. 树莓派系统常见中文字体
    """

    configured_path = str(getattr(cfg, "camera_overlay_font_path", "") or "").strip()
    candidates: list[str] = []
    if configured_path:
        candidates.append(configured_path)
    candidates.extend(FONT_CANDIDATES)

    for candidate in candidates:
        path = _resolve_path(candidate)
        if path.exists() and path.is_file():
            return str(path)
    return None


def _font_mask_signature(font, character: str) -> tuple:
    """
    获取单个字符渲染后的掩码特征。
    Pillow 遇到缺字时通常会绘制同一个 tofu 方框，用掩码特征可以识别并避开这类字体。
    """
    mask = font.getmask(character)
    return mask.size, mask.getbbox(), bytes(mask)


def _font_supports_text(font, text: str) -> bool:
    """
    判断字体是否覆盖待绘制文本。
    如果某个字符的渲染结果和缺字方框一致，就认为该字体不适合绘制这段文字。
    """
    if not text:
        return True

    missing_signature = _font_mask_signature(font, "\uffff")
    for character in text:
        if character.isspace():
            continue
        if _font_mask_signature(font, character) == missing_signature:
            return False
    return True


@lru_cache(maxsize=128)
def _load_font(font_size: int, sample_text: str = ""):
    """
    按文本内容选择可用字体。
    优先使用项目自带 Noto Sans SC；如果配置或系统字体缺字，会继续尝试后续候选，避免视频叠字出现方框。
    """
    configured_path = str(getattr(cfg, "camera_overlay_font_path", "") or "").strip()
    candidates: list[str] = []
    if configured_path:
        candidates.append(configured_path)
    candidates.extend(FONT_CANDIDATES)

    first_loadable_font = None
    for candidate in candidates:
        font_path = _resolve_path(candidate)
        if not font_path.exists() or not font_path.is_file():
            continue
        try:
            font = ImageFont.truetype(str(font_path), size=max(int(font_size), 12))
        except Exception:
            continue
        if first_loadable_font is None:
            first_loadable_font = font
        if _font_supports_text(font, sample_text):
            return font

    return first_loadable_font or ImageFont.load_default()


def draw_text_items(
    frame_bgr: np.ndarray,
    items: Iterable[dict],
) -> np.ndarray:
    """
    在单帧图像上批量绘制文本。

    这里统一走 Pillow，是为了在树莓派终端视频流中正确显示中文。
    外层一次性把本帧的所有文字交进来，避免反复 BGR/RGB 转换。
    """

    if frame_bgr is None or frame_bgr.size == 0:
        return frame_bgr

    rgb_frame = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    pil_image = Image.fromarray(rgb_frame)
    draw = ImageDraw.Draw(pil_image)

    for item in items:
        text = str(item.get("text", "") or "")
        if not text:
            continue

        position = tuple(item.get("position", (0, 0)))
        fill = _bgr_to_rgb(tuple(item.get("fill", (255, 255, 255))))
        stroke_fill = _bgr_to_rgb(tuple(item.get("stroke_fill", (0, 0, 0))))
        stroke_width = max(int(item.get("stroke_width", 0)), 0)
        font_size = max(int(item.get("font_size", 18)), 12)

        draw.text(
            xy=position,
            text=text,
            font=_load_font(font_size, text),
            fill=fill,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
        )

    return cv2.cvtColor(np.asarray(pil_image), cv2.COLOR_RGB2BGR)
