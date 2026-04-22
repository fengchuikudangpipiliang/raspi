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


FONT_CANDIDATES = (
    "static/fonts/NotoSansCJK-Regular.ttc",
    "static/fonts/NotoSansSC-Regular.otf",
    "static/fonts/SourceHanSansSC-Regular.otf",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
)


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
        path = Path(candidate)
        if path.exists() and path.is_file():
            return str(path)
    return None


@lru_cache(maxsize=32)
def _load_font(font_size: int):
    font_path = resolve_font_path()
    if font_path:
        try:
            return ImageFont.truetype(font_path, size=max(int(font_size), 12))
        except Exception:
            pass
    return ImageFont.load_default()


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
            font=_load_font(font_size),
            fill=fill,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
        )

    return cv2.cvtColor(np.asarray(pil_image), cv2.COLOR_RGB2BGR)
