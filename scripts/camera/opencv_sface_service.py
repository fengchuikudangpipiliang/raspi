from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from scripts.config.config import cfg


@dataclass
class SFaceCandidate:
    location: tuple[int, int, int, int]
    encoding: np.ndarray
    score: float


class OpenCVSFaceService:
    """
    OpenCV YuNet + SFace recognition backend.

    YuNet负责检测和5点关键点，SFace负责对齐裁剪和特征提取。它比当前 dlib/HOG
    链路更适合稍微侧脸、低清摄像头和现场门禁式识别。
    """

    def __init__(
        self,
        detector_model_path: Optional[str] = None,
        recognizer_model_path: Optional[str] = None,
        score_threshold: Optional[float] = None,
        nms_threshold: Optional[float] = None,
        top_k: Optional[int] = None,
    ):
        self.project_root = Path(__file__).resolve().parents[2]
        self.detector_model_path = self._resolve_path(detector_model_path or cfg.face_yunet_model_path)
        self.recognizer_model_path = self._resolve_path(recognizer_model_path or cfg.face_sface_model_path)
        self.score_threshold = float(score_threshold if score_threshold is not None else cfg.face_yunet_score_threshold)
        self.nms_threshold = float(nms_threshold if nms_threshold is not None else cfg.face_yunet_nms_threshold)
        self.top_k = int(top_k if top_k is not None else cfg.face_yunet_top_k)
        self.detector = None
        self.recognizer = None
        self.last_error = ""
        self._initialize()

    def is_available(self) -> bool:
        return self.detector is not None and self.recognizer is not None

    def detect_and_encode(self, frame_bgr: np.ndarray) -> list[SFaceCandidate]:
        if not self.is_available() or frame_bgr is None or frame_bgr.size == 0:
            return []

        height, width = frame_bgr.shape[:2]
        self.detector.setInputSize((int(width), int(height)))
        _, faces = self.detector.detect(frame_bgr)
        if faces is None or len(faces) == 0:
            return []

        candidates: list[SFaceCandidate] = []
        for face in faces:
            feature = self._feature_for_face(frame_bgr, face)
            if feature is None:
                continue
            candidates.append(
                SFaceCandidate(
                    location=self._face_to_location(face, width, height),
                    encoding=feature,
                    score=float(face[-1]) if len(face) >= 15 else 0.0,
                )
            )
        return candidates

    def encode_best_face(self, image_bgr: np.ndarray) -> Optional[np.ndarray]:
        candidates = self.detect_and_encode(image_bgr)
        if not candidates:
            return None
        best = max(candidates, key=lambda item: item.score)
        return best.encoding

    def _resolve_path(self, path_text: str) -> Path:
        path = Path((path_text or "").strip())
        if not path:
            return Path()
        if path.is_absolute():
            return path
        return (self.project_root / path).resolve()

    def _initialize(self) -> None:
        if not self.detector_model_path.exists():
            self.last_error = f"yunet_model_missing: {self.detector_model_path}"
            return
        if not self.recognizer_model_path.exists():
            self.last_error = f"sface_model_missing: {self.recognizer_model_path}"
            return
        if not hasattr(cv2, "FaceDetectorYN") or not hasattr(cv2, "FaceRecognizerSF"):
            self.last_error = "opencv_face_api_unavailable"
            return

        try:
            self.detector = cv2.FaceDetectorYN.create(
                str(self.detector_model_path),
                "",
                (320, 320),
                self.score_threshold,
                self.nms_threshold,
                self.top_k,
            )
            self.recognizer = cv2.FaceRecognizerSF.create(str(self.recognizer_model_path), "")
            self.last_error = ""
        except Exception as error:
            self.detector = None
            self.recognizer = None
            self.last_error = f"opencv_sface_init_failed: {error}"

    def _feature_for_face(self, frame_bgr: np.ndarray, face: np.ndarray) -> Optional[np.ndarray]:
        try:
            aligned = self.recognizer.alignCrop(frame_bgr, face)
            feature = self.recognizer.feature(aligned).reshape(-1).astype(np.float32)
        except Exception:
            return None
        norm = float(np.linalg.norm(feature))
        if norm <= 1e-8:
            return None
        return feature / norm

    def _face_to_location(self, face: np.ndarray, width: int, height: int) -> tuple[int, int, int, int]:
        x, y, box_width, box_height = [float(value) for value in face[:4]]
        left = max(int(round(x)), 0)
        top = max(int(round(y)), 0)
        right = min(int(round(x + box_width)), width)
        bottom = min(int(round(y + box_height)), height)
        return top, right, bottom, left
