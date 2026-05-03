import json
import random
import sqlite3
import time
import warnings
from collections import deque
from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from scripts.camera.anti_spoof_service import AntiSpoofService
from scripts.config.config import cfg

# `face_recognition_models` 仍然依赖 `pkg_resources`，在兼容版 setuptools 下会抛出
# 一条已知 deprecation warning。这里统一静默处理，避免树莓派终端启动日志被无关噪音刷屏。
warnings.filterwarnings(
    "ignore",
    message="pkg_resources is deprecated as an API.*",
    category=UserWarning,
    module="face_recognition_models",
)

try:
    import face_recognition
except Exception:
    face_recognition = None


@dataclass
class KnownFaceProfile:
    """
    单条已入库人脸档案。
    这里直接缓存编码向量，后续逐帧识别时不再反复查库。
    """

    face_profile_id: int
    user_id: int
    code: str
    name: str
    image_path: str
    encoding: np.ndarray


@dataclass
class PoseSummary:
    roll_angle: float
    yaw_offset: float
    signed_yaw: float
    pitch_ratio: float


@dataclass
class LivenessWindowSummary:
    sample_count: int
    checked_count: int
    avg_real_score: Optional[float]
    min_real_score: Optional[float]
    low_score_count: int
    gray_count: int
    avg_replay_risk_score: float
    max_replay_risk_score: float


@dataclass
class RecognitionResult:
    """
    单帧识别结果。
    这份结构后面既可以给本地识别线程用，也可以给调试日志或前端状态面板用。
    """

    ok: bool
    reason: str
    face_count: int
    recognized: bool = False
    attendance_ready: bool = False
    user_id: Optional[int] = None
    code: Optional[str] = None
    name: Optional[str] = None
    face_profile_id: Optional[int] = None
    distance: Optional[float] = None
    confidence: Optional[float] = None
    stable_count: int = 0
    required_count: int = 0
    cooldown_remaining_seconds: float = 0.0
    in_attendance_window: bool = True
    face_area_ratio: Optional[float] = None
    liveness_checked: bool = False
    liveness_passed: bool = False
    liveness_gray_zone: bool = False
    liveness_real_score: Optional[float] = None
    liveness_spoof_score: Optional[float] = None
    liveness_window_real_score: Optional[float] = None
    liveness_replay_risk_score: Optional[float] = None
    liveness_window_sample_count: int = 0
    blur_score: Optional[float] = None
    brightness_score: Optional[float] = None
    pose: Optional[PoseSummary] = None
    location: Optional[tuple[int, int, int, int]] = None
    timestamp: float = 0.0

    def to_dict(self) -> dict:
        payload = asdict(self)
        if self.pose is not None:
            payload["pose"] = asdict(self.pose)
        return payload


REASON_DISPLAY = {
    "not_started": "识别尚未开始",
    "empty_frame": "当前帧为空",
    "no_known_faces": "尚未加载已注册人脸档案",
    "no_face": "未检测到人脸",
    "multi_face": "检测到多张人脸，请保持单人入镜",
    "face_detection_failed": "人脸检测失败",
    "face_too_small": "人脸过小，请靠近摄像头",
    "liveness_disabled": "活体检测未启用",
    "liveness_model_unavailable": "活体模型暂不可用，当前按普通识别继续",
    "liveness_face_crop_failed": "活体检测失败，请重新正对镜头",
    "liveness_uncertain": "活体结果不够稳定，请正对镜头后重试",
    "spoof_suspected": "疑似照片或翻拍，请真人到场签到",
    "liveness_passed": "活体检测通过",
    "liveness_challenge_turn_left": "请轻微向左转头",
    "liveness_challenge_turn_right": "请轻微向右转头",
    "liveness_challenge_front": "请转回正脸",
    "liveness_challenge_timeout": "动作确认超时，请重新开始",
    "image_blurry": "画面偏模糊，请保持稳定",
    "bad_lighting": "光线不合适，请调整亮度",
    "landmarks_missing": "关键点提取失败，请正视镜头",
    "landmarks_incomplete": "关键点不完整，请调整姿态",
    "roll_too_large": "头部倾斜过大，请摆正头部",
    "yaw_too_large": "侧脸角度过大，请正视镜头",
    "pitch_bad": "抬头或低头幅度过大",
    "face_encoding_failed": "人脸编码失败，请重试",
    "unknown": "未匹配到已注册人脸",
    "ambiguous_match": "匹配结果过近，请单人重新识别",
    "match_not_stable_yet": "已匹配到身份，正在等待稳定帧",
    "outside_attendance_window": "当前不在考勤时间段内",
    "attendance_cooldown": "刚完成签到，请稍后再试",
    "attendance_ready": "识别稳定，准备写入考勤",
}


class StrictFaceRecognizer:
    """
    严格版树莓派摄像头人脸识别器。

    设计目标：
    1. 只识别已经正式注册并入库的人脸编码。
    2. 单人入镜、正脸、清晰、亮度合理，任何一项不满足就拒绝。
    3. 多帧稳定命中后才认为“真的识别成功”，降低瞬时误识别。
    4. 识别成功后走冷却时间，避免摄像头前停留时重复考勤。

    当前文件不接入现有摄像头线程，只提供可复用的识别能力。
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        face_distance_threshold: Optional[float] = None,
        match_required_times: Optional[int] = None,
        unknown_face_label: Optional[str] = None,
        detection_scale: float = 0.6,
        min_face_area_ratio: float = 0.03,
        min_blur_score: float = 0.0,
        brightness_min: float = 0.0,
        brightness_max: float = 255.0,
        max_roll_angle: float = 180.0,
        max_yaw_offset: float = 1.0,
        min_pitch_ratio: float = -1.0,
        max_pitch_ratio: float = 2.0,
        ambiguity_margin: float = 0.02,
        stable_timeout_seconds: float = 1.8,
        attendance_cooldown_seconds: Optional[int] = None,
    ):
        if face_recognition is None:
            raise RuntimeError("face_recognition 模块不可用，无法启动严格识别器。")

        self.db_path = Path(db_path or cfg.sqlite_path)
        self.face_distance_threshold = float(face_distance_threshold or cfg.face_distance_threshold)
        self.match_required_times = max(int(match_required_times or cfg.face_match_required_times), 1)
        self.unknown_face_label = unknown_face_label or cfg.unknown_face_label
        self.detection_scale = min(max(float(detection_scale), 0.20), 1.0)
        self.min_face_area_ratio = float(min_face_area_ratio)
        self.min_blur_score = float(min_blur_score)
        self.brightness_min = float(brightness_min)
        self.brightness_max = float(brightness_max)
        self.max_roll_angle = float(max_roll_angle)
        self.max_yaw_offset = float(max_yaw_offset)
        self.min_pitch_ratio = float(min_pitch_ratio)
        self.max_pitch_ratio = float(max_pitch_ratio)
        self.ambiguity_margin = float(ambiguity_margin)
        self.stable_timeout_seconds = float(stable_timeout_seconds)
        self.attendance_cooldown_seconds = int(attendance_cooldown_seconds or cfg.attendance_cooldown_seconds)
        self.liveness_service = AntiSpoofService()
        self.liveness_fail_required_times = max(int(cfg.attendance_liveness_fail_required_times), 1)
        self.liveness_window_seconds = max(float(cfg.attendance_liveness_window_seconds), 0.5)
        self.liveness_window_min_samples = max(int(cfg.attendance_liveness_window_min_samples), 1)
        self.liveness_window_real_threshold = float(cfg.attendance_liveness_window_real_threshold)
        self.liveness_window_replay_risk_threshold = float(cfg.attendance_liveness_window_replay_risk_threshold)
        self.liveness_window_uncertain_real_threshold = float(cfg.attendance_liveness_window_uncertain_real_threshold)
        self.liveness_window_uncertain_replay_risk_threshold = float(cfg.attendance_liveness_window_uncertain_replay_risk_threshold)
        self.liveness_challenge_enabled = bool(cfg.attendance_liveness_challenge_enabled)
        self.liveness_challenge_mode = str(cfg.attendance_liveness_challenge_mode or "risk").strip().lower()
        self.liveness_challenge_ttl_seconds = max(float(cfg.attendance_liveness_challenge_ttl_seconds), 3.0)
        self.liveness_challenge_pass_seconds = max(float(cfg.attendance_liveness_challenge_pass_seconds), 1.0)
        self.liveness_challenge_front_yaw_max = float(cfg.attendance_liveness_challenge_front_yaw_max)
        self.liveness_challenge_side_yaw_min = float(cfg.attendance_liveness_challenge_side_yaw_min)
        self.liveness_challenge_side_yaw_max = float(cfg.attendance_liveness_challenge_side_yaw_max)
        self.liveness_challenge_distance_ratio = float(cfg.attendance_liveness_challenge_distance_ratio)

        self.known_profiles: list[KnownFaceProfile] = []
        self.known_encodings: list[np.ndarray] = []
        self._stable_user_id: Optional[int] = None
        self._stable_face_profile_id: Optional[int] = None
        self._stable_count = 0
        self._last_stable_at = 0.0
        self._last_attendance_at: dict[int, float] = {}
        self._last_result: Optional[RecognitionResult] = None
        self._liveness_low_score_count = 0
        self._liveness_window = deque()
        self._challenge_user_id: Optional[int] = None
        self._challenge_face_profile_id: Optional[int] = None
        self._challenge_direction: Optional[str] = None
        self._challenge_step: Optional[str] = None
        self._challenge_expires_at = 0.0
        self._challenge_passed_until: dict[int, float] = {}

    def reload_known_faces(self) -> int:
        """
        从 SQLite 重新加载所有可识别的人脸档案。
        只加载状态正常且已经正式注册的用户。
        """

        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                """
                SELECT
                    face_profiles.id AS face_profile_id,
                    face_profiles.user_id AS user_id,
                    users.code AS code,
                    users.name AS name,
                    face_profiles.image_path AS image_path,
                    face_profiles.encoding AS encoding
                FROM face_profiles
                JOIN users ON users.id = face_profiles.user_id
                LEFT JOIN roster_members ON roster_members.id = users.roster_member_id
                WHERE
                    users.password_hash IS NOT NULL
                    AND IFNULL(roster_members.status, 'active') = 'active'
                    AND face_profiles.review_status = 'approved'
                ORDER BY face_profiles.id ASC
                """
            ).fetchall()
        finally:
            connection.close()

        profiles: list[KnownFaceProfile] = []
        encodings: list[np.ndarray] = []
        for row in rows:
            try:
                vector = np.asarray(json.loads(row["encoding"]), dtype=np.float32)
            except Exception:
                continue
            if vector.ndim != 1 or vector.size != 128:
                continue

            profiles.append(
                KnownFaceProfile(
                    face_profile_id=int(row["face_profile_id"]),
                    user_id=int(row["user_id"]),
                    code=str(row["code"]),
                    name=str(row["name"]),
                    image_path=str(row["image_path"]),
                    encoding=vector,
                )
            )
            encodings.append(vector)

        self.known_profiles = profiles
        self.known_encodings = encodings
        self.reset_tracking()
        return len(self.known_profiles)

    def reset_tracking(self) -> None:
        """
        清空多帧稳定识别的中间状态。
        """

        self._stable_user_id = None
        self._stable_face_profile_id = None
        self._stable_count = 0
        self._last_stable_at = 0.0

    def prepare_frame(self, frame_bgr: np.ndarray) -> np.ndarray:
        """
        统一对摄像头帧做镜像和旋转处理。
        接入摄像头线程时可以先调这个函数，再把结果同时交给识别和画面输出。
        """

        return self._normalize_frame(frame_bgr)

    def process_frame(
        self,
        frame_bgr: np.ndarray,
        now: Optional[float] = None,
        frame_already_normalized: bool = False,
    ) -> RecognitionResult:
        """
        对单帧 BGR 图像做严格人脸识别。
        输入应直接来自 OpenCV 摄像头帧。
        """

        timestamp = float(now or time.time())
        result = RecognitionResult(
            ok=False,
            reason="not_started",
            face_count=0,
            required_count=self.match_required_times,
            timestamp=timestamp,
        )

        if frame_bgr is None or not isinstance(frame_bgr, np.ndarray) or frame_bgr.size == 0:
            result.reason = "empty_frame"
            self._reset_on_failed_frame()
            self._last_result = result
            return result

        if not self.known_profiles:
            result.reason = "no_known_faces"
            self._reset_on_failed_frame()
            self._last_result = result
            return result

        if not frame_already_normalized:
            frame_bgr = self._normalize_frame(frame_bgr)
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        height, width = frame_bgr.shape[:2]

        small_rgb = cv2.resize(frame_rgb, (0, 0), fx=self.detection_scale, fy=self.detection_scale)
        try:
            small_locations = face_recognition.face_locations(
                small_rgb,
                model=cfg.face_detection_model,
            )
        except Exception:
            result.reason = "face_detection_failed"
            self._reset_on_failed_frame()
            self._last_result = result
            return result

        locations = [self._scale_location(location) for location in small_locations]
        result.face_count = len(locations)
        if not locations:
            result.reason = "no_face"
            self._reset_on_failed_frame()
            self._last_result = result
            return result
        if len(locations) > 1:
            result.reason = "multi_face"
            self._reset_on_failed_frame()
            self._last_result = result
            return result

        location = locations[0]
        result.location = location
        result.face_area_ratio = self._calculate_face_area_ratio(location, width, height)
        if result.face_area_ratio < self.min_face_area_ratio:
            result.reason = "face_too_small"
            self._reset_on_failed_frame()
            self._last_result = result
            return result

        face_roi = self._extract_face_roi(frame_bgr, location)
        liveness_result = self.liveness_service.analyze_face(face_roi)
        replay_risk_score = self._estimate_replay_risk_score(face_roi)
        liveness_summary = self._add_liveness_sample(timestamp, liveness_result, replay_risk_score)
        result.liveness_checked = liveness_result.checked
        result.liveness_passed = liveness_result.passed
        result.liveness_gray_zone = liveness_result.gray_zone
        result.liveness_real_score = liveness_result.real_score
        result.liveness_spoof_score = liveness_result.spoof_score
        result.liveness_replay_risk_score = replay_risk_score
        result.liveness_window_sample_count = liveness_summary.sample_count
        result.liveness_window_real_score = liveness_summary.avg_real_score
        self._liveness_low_score_count = liveness_summary.low_score_count

        encodings = face_recognition.face_encodings(
            frame_rgb,
            known_face_locations=[location],
            num_jitters=1,
            model="small",
        )
        if not encodings:
            result.reason = "face_encoding_failed"
            self._reset_on_failed_frame()
            self._last_result = result
            return result

        query_encoding = encodings[0]
        distances = face_recognition.face_distance(self.known_encodings, query_encoding)
        best_index = int(np.argmin(distances))
        best_distance = float(distances[best_index])
        result.distance = best_distance

        if best_distance > self.face_distance_threshold:
            result.reason = self.unknown_face_label
            self._reset_on_failed_frame()
            self._last_result = result
            return result

        if len(distances) > 1:
            sorted_distances = np.sort(distances)
            second_distance = float(sorted_distances[1])
            if second_distance - best_distance < self.ambiguity_margin:
                result.reason = "ambiguous_match"
                self._reset_on_failed_frame()
                self._last_result = result
                return result

        matched_profile = self.known_profiles[best_index]
        result.user_id = matched_profile.user_id
        result.face_profile_id = matched_profile.face_profile_id
        result.code = matched_profile.code
        result.name = matched_profile.name
        result.recognized = True
        result.confidence = self._distance_to_confidence(best_distance)

        result.stable_count = self._advance_stability(
            user_id=matched_profile.user_id,
            face_profile_id=matched_profile.face_profile_id,
            timestamp=timestamp,
        )
        if result.stable_count < self.match_required_times:
            result.reason = "match_not_stable_yet"
            result.ok = True
            self._last_result = result
            return result

        liveness_decision = self._evaluate_passive_liveness(liveness_summary)
        if liveness_decision:
            result.reason = liveness_decision
            result.ok = liveness_decision == "liveness_uncertain"
            if liveness_decision == "spoof_suspected":
                self._reset_on_failed_frame()
            self._last_result = result
            return result

        if not self._is_within_attendance_window(timestamp):
            result.reason = "outside_attendance_window"
            result.ok = True
            result.in_attendance_window = False
            self._last_result = result
            return result

        cooldown_remaining = self._cooldown_remaining_seconds(matched_profile.user_id, timestamp)
        result.cooldown_remaining_seconds = cooldown_remaining
        if cooldown_remaining > 0:
            result.reason = "attendance_cooldown"
            result.ok = True
            self._last_result = result
            return result

        if self._should_require_liveness_challenge(
            result=result,
            liveness_gray_zone=liveness_result.gray_zone,
            distance=best_distance,
            timestamp=timestamp,
        ):
            challenge_reason = self._advance_liveness_challenge(
                frame_rgb=frame_rgb,
                location=location,
                user_id=matched_profile.user_id,
                face_profile_id=matched_profile.face_profile_id,
                timestamp=timestamp,
            )
            if challenge_reason:
                result.reason = challenge_reason
                result.ok = True
                self._last_result = result
                return result

        result.ok = True
        result.reason = "attendance_ready"
        result.attendance_ready = True
        self._last_result = result
        return result

    def annotate_frame(self, frame_bgr: np.ndarray, result: Optional[RecognitionResult] = None) -> np.ndarray:
        """
        当前终端页不再在实时视频上绘制调试 HUD。
        这里只保留接口，便于后续需要时恢复调试叠加。
        """

        if frame_bgr is None or frame_bgr.size == 0:
            return frame_bgr
        return frame_bgr.copy()

    def known_faces_count(self) -> int:
        return len(self.known_profiles)

    def mark_attendance_committed(self, user_id: int, timestamp: Optional[float] = None) -> None:
        """
        由外层在真正写入考勤记录成功后调用，开始该用户的冷却时间。
        """

        self._last_attendance_at[user_id] = float(timestamp or time.time())

    def get_last_result(self) -> Optional[RecognitionResult]:
        return self._last_result

    def describe_reason(self, reason: str) -> str:
        """
        把内部原因码转成终端页可读的中文说明。
        """

        if reason == self.unknown_face_label:
            return REASON_DISPLAY.get("unknown", str(reason))
        return REASON_DISPLAY.get(reason, str(reason))

    def _reset_on_failed_frame(self) -> None:
        self.reset_tracking()
        self._liveness_low_score_count = 0
        self._liveness_window.clear()
        self._reset_liveness_challenge()

    def _add_liveness_sample(self, timestamp: float, liveness_result, replay_risk_score: float) -> LivenessWindowSummary:
        self._liveness_window.append(
            {
                "timestamp": timestamp,
                "checked": bool(liveness_result.checked),
                "passed": bool(liveness_result.passed),
                "gray_zone": bool(liveness_result.gray_zone),
                "real_score": liveness_result.real_score,
                "replay_risk_score": float(replay_risk_score),
            }
        )

        cutoff = timestamp - self.liveness_window_seconds
        while self._liveness_window and self._liveness_window[0]["timestamp"] < cutoff:
            self._liveness_window.popleft()

        return self._summarize_liveness_window()

    def _summarize_liveness_window(self) -> LivenessWindowSummary:
        samples = list(self._liveness_window)
        checked_samples = [sample for sample in samples if sample["checked"]]
        real_scores = [
            float(sample["real_score"])
            for sample in checked_samples
            if sample.get("real_score") is not None
        ]
        replay_scores = [float(sample["replay_risk_score"]) for sample in samples]
        low_score_count = sum(
            1
            for sample in checked_samples
            if sample.get("real_score") is not None
            and float(sample["real_score"]) < self.liveness_service.gray_threshold
        )
        gray_count = sum(1 for sample in checked_samples if sample["gray_zone"])
        return LivenessWindowSummary(
            sample_count=len(samples),
            checked_count=len(checked_samples),
            avg_real_score=float(np.mean(real_scores)) if real_scores else None,
            min_real_score=float(np.min(real_scores)) if real_scores else None,
            low_score_count=low_score_count,
            gray_count=gray_count,
            avg_replay_risk_score=float(np.mean(replay_scores)) if replay_scores else 0.0,
            max_replay_risk_score=float(np.max(replay_scores)) if replay_scores else 0.0,
        )

    def _evaluate_passive_liveness(self, summary: LivenessWindowSummary) -> Optional[str]:
        if not self.liveness_service.enabled or summary.checked_count == 0:
            return None
        if summary.checked_count < self.liveness_window_min_samples:
            return "liveness_uncertain"
        if summary.low_score_count >= self.liveness_fail_required_times:
            return "spoof_suspected"
        if summary.max_replay_risk_score >= self.liveness_window_replay_risk_threshold:
            return "spoof_suspected"
        if (
            summary.avg_real_score is not None
            and summary.avg_real_score < self.liveness_window_uncertain_real_threshold
            and summary.avg_replay_risk_score >= self.liveness_window_uncertain_replay_risk_threshold
        ):
            return "spoof_suspected"
        if summary.avg_real_score is not None and summary.avg_real_score < self.liveness_window_real_threshold:
            return "liveness_uncertain"
        if summary.avg_replay_risk_score >= self.liveness_window_uncertain_replay_risk_threshold:
            return "liveness_uncertain"
        return None

    def _estimate_replay_risk_score(self, face_roi: np.ndarray) -> float:
        if face_roi is None or not isinstance(face_roi, np.ndarray) or face_roi.size == 0:
            return 0.0

        resized = cv2.resize(face_roi, (96, 96), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)
        saturation = hsv[:, :, 1]
        value = hsv[:, :, 2]

        glare_ratio = float(np.mean((value > 245) & (saturation < 70)))
        glare_risk = self._clamp01((glare_ratio - 0.02) / 0.10)

        edges = cv2.Canny(gray, 80, 160)
        edge_density = float(np.mean(edges > 0))
        edge_risk = self._clamp01((edge_density - 0.18) / 0.20)

        gray_float = gray.astype(np.float32)
        gray_float -= float(gray_float.mean())
        spectrum = np.fft.fftshift(np.fft.fft2(gray_float))
        magnitude = np.abs(spectrum)
        rows, cols = magnitude.shape
        y_grid, x_grid = np.ogrid[:rows, :cols]
        radius = np.sqrt((y_grid - rows / 2.0) ** 2 + (x_grid - cols / 2.0) ** 2)
        normalized_radius = radius / max(min(rows, cols) / 2.0, 1.0)
        high_frequency_energy = float(magnitude[normalized_radius >= 0.45].sum())
        total_energy = float(magnitude.sum()) + 1e-6
        high_frequency_ratio = high_frequency_energy / total_energy
        moire_risk = self._clamp01((high_frequency_ratio - 0.36) / 0.22)

        return self._clamp01((0.45 * moire_risk) + (0.35 * glare_risk) + (0.20 * edge_risk))

    def _clamp01(self, value: float) -> float:
        return max(0.0, min(float(value), 1.0))

    def _reset_liveness_challenge(self) -> None:
        self._challenge_user_id = None
        self._challenge_face_profile_id = None
        self._challenge_direction = None
        self._challenge_step = None
        self._challenge_expires_at = 0.0

    def _should_require_liveness_challenge(
        self,
        result: RecognitionResult,
        liveness_gray_zone: bool,
        distance: float,
        timestamp: float,
    ) -> bool:
        if not self.liveness_challenge_enabled or result.user_id is None:
            return False
        if self._challenge_passed_until.get(result.user_id, 0.0) >= timestamp:
            return False

        mode = self.liveness_challenge_mode
        if mode in {"off", "disabled", "false", "none"}:
            return False
        if mode == "always":
            return True

        distance_ratio = distance / max(self.face_distance_threshold, 1e-6)
        return (
            bool(liveness_gray_zone)
            or self._liveness_low_score_count > 0
            or distance_ratio >= self.liveness_challenge_distance_ratio
        )

    def _advance_liveness_challenge(
        self,
        frame_rgb: np.ndarray,
        location: tuple[int, int, int, int],
        user_id: int,
        face_profile_id: int,
        timestamp: float,
    ) -> Optional[str]:
        if self._challenge_passed_until.get(user_id, 0.0) >= timestamp:
            return None

        if (
            self._challenge_user_id != user_id
            or self._challenge_face_profile_id != face_profile_id
            or self._challenge_direction not in {"left", "right"}
            or self._challenge_step not in {"left", "right", "front"}
        ):
            return self._start_liveness_challenge(user_id, face_profile_id, timestamp)

        if timestamp > self._challenge_expires_at:
            self._reset_liveness_challenge()
            return self._start_liveness_challenge(user_id, face_profile_id, timestamp)

        try:
            landmarks_list = face_recognition.face_landmarks(frame_rgb, face_locations=[location])
            if not landmarks_list:
                return self._current_challenge_reason()
            pose = self._calculate_pose_metrics(landmarks_list[0])
        except Exception:
            return self._current_challenge_reason()

        if self._challenge_step in {"left", "right"}:
            if self._pose_matches_turn(pose, self._challenge_step):
                self._challenge_step = "front"
                return "liveness_challenge_front"
            return self._current_challenge_reason()

        if self._challenge_step == "front":
            if pose.yaw_offset <= self.liveness_challenge_front_yaw_max:
                self._challenge_passed_until[user_id] = timestamp + self.liveness_challenge_pass_seconds
                self._reset_liveness_challenge()
                return None
            return "liveness_challenge_front"

        return self._start_liveness_challenge(user_id, face_profile_id, timestamp)

    def _start_liveness_challenge(self, user_id: int, face_profile_id: int, timestamp: float) -> str:
        direction = random.choice(("left", "right"))
        self._challenge_user_id = user_id
        self._challenge_face_profile_id = face_profile_id
        self._challenge_direction = direction
        self._challenge_step = direction
        self._challenge_expires_at = timestamp + self.liveness_challenge_ttl_seconds
        return self._current_challenge_reason()

    def _current_challenge_reason(self) -> str:
        if self._challenge_step == "left":
            return "liveness_challenge_turn_left"
        if self._challenge_step == "right":
            return "liveness_challenge_turn_right"
        return "liveness_challenge_front"

    def _pose_matches_turn(self, pose: PoseSummary, direction: str) -> bool:
        if abs(pose.signed_yaw) > self.liveness_challenge_side_yaw_max:
            return False
        if direction == "left":
            return pose.signed_yaw <= -self.liveness_challenge_side_yaw_min
        if direction == "right":
            return pose.signed_yaw >= self.liveness_challenge_side_yaw_min
        return False

    def _normalize_frame(self, frame_bgr: np.ndarray) -> np.ndarray:
        frame = frame_bgr
        if cfg.camera_mirror:
            frame = cv2.flip(frame, 1)
        if cfg.camera_rotate in {90, 180, 270}:
            rotate_map = {
                90: cv2.ROTATE_90_CLOCKWISE,
                180: cv2.ROTATE_180,
                270: cv2.ROTATE_90_COUNTERCLOCKWISE,
            }
            frame = cv2.rotate(frame, rotate_map[cfg.camera_rotate])
        return frame

    def _scale_location(self, location: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        top, right, bottom, left = location
        scale = max(self.detection_scale, 1e-6)
        return (
            int(top / scale),
            int(right / scale),
            int(bottom / scale),
            int(left / scale),
        )

    def _calculate_face_area_ratio(self, location: tuple[int, int, int, int], width: int, height: int) -> float:
        top, right, bottom, left = location
        face_area = max(right - left, 0) * max(bottom - top, 0)
        image_area = max(width * height, 1)
        return face_area / image_area

    def _extract_face_roi(self, frame_bgr: np.ndarray, location: tuple[int, int, int, int]) -> np.ndarray:
        top, right, bottom, left = location
        margin_x = int((right - left) * 0.08)
        margin_y = int((bottom - top) * 0.08)
        top = max(top - margin_y, 0)
        bottom = min(bottom + margin_y, frame_bgr.shape[0])
        left = max(left - margin_x, 0)
        right = min(right + margin_x, frame_bgr.shape[1])
        return frame_bgr[top:bottom, left:right]

    def _estimate_blur_score(self, face_roi: np.ndarray) -> float:
        if face_roi.size == 0:
            return 0.0
        gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())

    def _estimate_brightness_score(self, face_roi: np.ndarray) -> float:
        if face_roi.size == 0:
            return 0.0
        gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
        return float(gray.mean())

    def _calculate_pose_metrics(self, landmarks: dict) -> PoseSummary:
        required_keys = ("left_eye", "right_eye", "nose_tip", "top_lip", "bottom_lip")
        missing = [key for key in required_keys if not landmarks.get(key)]
        if missing:
            raise ValueError(f"missing landmarks: {missing}")

        left_eye = self._center_point(landmarks["left_eye"])
        right_eye = self._center_point(landmarks["right_eye"])
        nose_tip = self._center_point(landmarks["nose_tip"])
        mouth_points = landmarks["top_lip"] + landmarks["bottom_lip"]
        mouth_center = self._center_point(mouth_points)

        roll_angle = abs(np.degrees(np.arctan2(right_eye[1] - left_eye[1], right_eye[0] - left_eye[0])))
        eye_center_x = (left_eye[0] + right_eye[0]) / 2.0
        eye_distance = max(abs(right_eye[0] - left_eye[0]), 1.0)
        signed_yaw = (nose_tip[0] - eye_center_x) / eye_distance
        yaw_offset = abs(signed_yaw)
        eye_center_y = (left_eye[1] + right_eye[1]) / 2.0
        vertical_span = max(abs(mouth_center[1] - eye_center_y), 1.0)
        pitch_ratio = (nose_tip[1] - eye_center_y) / vertical_span
        return PoseSummary(
            roll_angle=float(roll_angle),
            yaw_offset=float(yaw_offset),
            signed_yaw=float(signed_yaw),
            pitch_ratio=float(pitch_ratio),
        )

    def _center_point(self, points: list[tuple[int, int]]) -> tuple[float, float]:
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        return (float(sum(xs) / len(xs)), float(sum(ys) / len(ys)))

    def _distance_to_confidence(self, distance: float) -> float:
        threshold = max(self.face_distance_threshold, 1e-6)
        raw = 1.0 - (distance / threshold)
        return max(0.0, min(raw, 1.0))

    def _advance_stability(self, user_id: int, face_profile_id: int, timestamp: float) -> int:
        if (
            self._stable_user_id == user_id
            and self._stable_face_profile_id == face_profile_id
            and (timestamp - self._last_stable_at) <= self.stable_timeout_seconds
        ):
            self._stable_count += 1
        else:
            self._stable_user_id = user_id
            self._stable_face_profile_id = face_profile_id
            self._stable_count = 1

        self._last_stable_at = timestamp
        return self._stable_count

    def _cooldown_remaining_seconds(self, user_id: int, timestamp: float) -> float:
        last_ts = self._last_attendance_at.get(user_id)
        if last_ts is None:
            return 0.0
        remaining = self.attendance_cooldown_seconds - (timestamp - last_ts)
        return max(float(round(remaining, 3)), 0.0)

    def _is_within_attendance_window(self, timestamp: float) -> bool:
        now = datetime.fromtimestamp(timestamp).astimezone()
        current_minutes = now.hour * 60 + now.minute
        start_minutes = self._parse_minutes(cfg.attendance_start_time)
        end_minutes = self._parse_minutes(cfg.attendance_end_time)
        if start_minutes <= end_minutes:
            return start_minutes <= current_minutes <= end_minutes
        return current_minutes >= start_minutes or current_minutes <= end_minutes

    def _parse_minutes(self, text: str) -> int:
        value = (text or "").strip()
        try:
            hour_text, minute_text = value.split(":", 1)
            hour = max(0, min(int(hour_text), 23))
            minute = max(0, min(int(minute_text), 59))
            return hour * 60 + minute
        except Exception:
            return 0
