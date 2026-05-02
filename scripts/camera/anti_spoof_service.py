from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from scripts.config.config import cfg


@dataclass
class AntiSpoofResult:
    """
    单次被动活体检测结果。
    第一版只做前置二分类，用来判断当前人脸更像真人还是更像翻拍/照片。
    """

    checked: bool
    available: bool
    passed: bool
    gray_zone: bool
    reason: str
    real_score: Optional[float] = None
    spoof_score: Optional[float] = None


class AntiSpoofService:
    """
    OpenVINO 被动活体检测服务。

    当前职责：
    1. 加载 `anti-spoof-mn3` IR 模型。
    2. 接收裁剪后的人脸 BGR 图像。
    3. 返回真人/伪造分数与第一版门禁结果。
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        device_name: Optional[str] = None,
        real_threshold: Optional[float] = None,
        gray_threshold: Optional[float] = None,
        enabled: Optional[bool] = None,
    ):
        self.project_root = Path(__file__).resolve().parents[2]
        self.enabled = cfg.attendance_liveness_enabled if enabled is None else bool(enabled)
        self.model_path = self._resolve_model_path(model_path or cfg.attendance_liveness_model_path)
        self.device_name = (device_name or cfg.attendance_liveness_device or "CPU").strip() or "CPU"
        self.real_threshold = float(real_threshold if real_threshold is not None else cfg.attendance_liveness_real_threshold)
        self.gray_threshold = float(gray_threshold if gray_threshold is not None else cfg.attendance_liveness_gray_threshold)
        self.last_error = ""
        self._core = None
        self._compiled_model = None
        self._infer_request = None
        self._input_name = ""
        self._output_name = ""
        self._input_height = 128
        self._input_width = 128
        if self.enabled:
            self._initialize()

    def is_available(self) -> bool:
        return self.enabled and self._compiled_model is not None and self._infer_request is not None

    def analyze_face(self, face_roi_bgr: np.ndarray) -> AntiSpoofResult:
        """
        对单张裁剪后的人脸图做被动活体检测。
        如果模型未启用或暂时不可用，这里默认放行，避免终端直接全量瘫痪。
        """

        if not self.enabled:
            return AntiSpoofResult(
                checked=False,
                available=False,
                passed=True,
                gray_zone=False,
                reason="liveness_disabled",
            )
        if not self.is_available():
            return AntiSpoofResult(
                checked=False,
                available=False,
                passed=True,
                gray_zone=False,
                reason="liveness_model_unavailable",
            )
        if face_roi_bgr is None or not isinstance(face_roi_bgr, np.ndarray) or face_roi_bgr.size == 0:
            return AntiSpoofResult(
                checked=True,
                available=True,
                passed=False,
                gray_zone=False,
                reason="liveness_face_crop_failed",
            )

        input_tensor = self._preprocess(face_roi_bgr)
        self._infer_request.infer({self._input_name: input_tensor})
        raw_scores = np.asarray(self._infer_request.get_tensor(self._output_name).data).reshape(-1).astype(np.float32)
        real_score, spoof_score = self._normalize_scores(raw_scores)
        if real_score >= self.real_threshold:
            return AntiSpoofResult(
                checked=True,
                available=True,
                passed=True,
                gray_zone=False,
                reason="liveness_passed",
                real_score=real_score,
                spoof_score=spoof_score,
            )

        in_gray_zone = real_score >= self.gray_threshold
        return AntiSpoofResult(
            checked=True,
            available=True,
            passed=False,
            gray_zone=in_gray_zone,
            reason="liveness_uncertain" if in_gray_zone else "spoof_suspected",
            real_score=real_score,
            spoof_score=spoof_score,
        )

    def _resolve_model_path(self, path_text: str) -> Path:
        path = Path((path_text or "").strip())
        if not path:
            return Path()
        if path.is_absolute():
            return path
        return (self.project_root / path).resolve()

    def _initialize(self) -> None:
        """
        初始化 OpenVINO 模型。
        如果模型文件缺失或运行时不可用，这里记录错误并降级为“不执行活体门禁”。
        """

        if not self.model_path or not self.model_path.exists():
            self.last_error = f"model_missing: {self.model_path}"
            return
        try:
            from openvino import Core
        except Exception as error:
            self.last_error = f"openvino_import_failed: {error}"
            return

        try:
            self._core = Core()
            model = self._core.read_model(model=str(self.model_path))
            self._compiled_model = self._core.compile_model(model=model, device_name=self.device_name)
            self._infer_request = self._compiled_model.create_infer_request()
            input_port = self._compiled_model.inputs[0]
            output_port = self._compiled_model.outputs[0]
            self._input_name = input_port.any_name
            self._output_name = output_port.any_name
            shape = [int(dim) for dim in input_port.shape]
            if len(shape) == 4:
                self._input_height = max(shape[2], 1)
                self._input_width = max(shape[3], 1)
            self.last_error = ""
        except Exception as error:
            self._compiled_model = None
            self._infer_request = None
            self.last_error = f"model_init_failed: {error}"

    def _preprocess(self, face_roi_bgr: np.ndarray) -> np.ndarray:
        """
        按 `anti-spoof-mn3` IR 期望格式准备输入。
        转换后的 IR 已经内嵌了均值、尺度和通道翻转，因此这里只做 BGR resize + NCHW。
        """

        resized = cv2.resize(face_roi_bgr, (self._input_width, self._input_height))
        tensor = resized.astype(np.float32)
        tensor = np.transpose(tensor, (2, 0, 1))
        return np.expand_dims(tensor, axis=0)

    def _normalize_scores(self, raw_scores: np.ndarray) -> tuple[float, float]:
        """
        模型说明里输出已经是概率，但这里仍做一次兜底归一化，避免遇到 logits 形式时结果失真。
        """

        if raw_scores.size < 2:
            return 0.0, 1.0
        values = raw_scores[:2].astype(np.float64)
        if np.all(values >= 0.0) and np.all(values <= 1.0) and abs(float(values.sum()) - 1.0) <= 0.05:
            real_score = float(values[0])
            spoof_score = float(values[1])
            return real_score, spoof_score

        shifted = values - np.max(values)
        exp_values = np.exp(shifted)
        probs = exp_values / max(float(exp_values.sum()), 1e-8)
        return float(probs[0]), float(probs[1])
