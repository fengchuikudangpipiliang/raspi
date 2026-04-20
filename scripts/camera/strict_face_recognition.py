import json
import sqlite3
import time
from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from scripts.config.config import cfg

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
        detection_scale: float = 0.5,
        min_face_area_ratio: float = 0.10,
        min_blur_score: float = 110.0,
        brightness_min: float = 60.0,
        brightness_max: float = 195.0,
        max_roll_angle: float = 12.0,
        max_yaw_offset: float = 0.18,
        min_pitch_ratio: float = 0.32,
        max_pitch_ratio: float = 0.78,
        ambiguity_margin: float = 0.03,
        stable_timeout_seconds: float = 1.2,
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

        self.known_profiles: list[KnownFaceProfile] = []
        self.known_encodings: list[np.ndarray] = []
        self._stable_user_id: Optional[int] = None
        self._stable_face_profile_id: Optional[int] = None
        self._stable_count = 0
        self._last_stable_at = 0.0
        self._last_attendance_at: dict[int, float] = {}
        self._last_result: Optional[RecognitionResult] = None

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

    def process_frame(self, frame_bgr: np.ndarray, now: Optional[float] = None) -> RecognitionResult:
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

        roi = self._extract_face_roi(frame_bgr, location)
        result.blur_score = self._estimate_blur_score(roi)
        if result.blur_score < self.min_blur_score:
            result.reason = "image_blurry"
            self._reset_on_failed_frame()
            self._last_result = result
            return result

        result.brightness_score = self._estimate_brightness_score(roi)
        if not (self.brightness_min <= result.brightness_score <= self.brightness_max):
            result.reason = "bad_lighting"
            self._reset_on_failed_frame()
            self._last_result = result
            return result

        landmarks = face_recognition.face_landmarks(frame_rgb, [location])
        if not landmarks:
            result.reason = "landmarks_missing"
            self._reset_on_failed_frame()
            self._last_result = result
            return result

        try:
            pose = self._calculate_pose_metrics(landmarks[0])
        except ValueError:
            result.reason = "landmarks_incomplete"
            self._reset_on_failed_frame()
            self._last_result = result
            return result

        result.pose = pose
        if pose.roll_angle > self.max_roll_angle:
            result.reason = "roll_too_large"
            self._reset_on_failed_frame()
            self._last_result = result
            return result
        if pose.yaw_offset > self.max_yaw_offset:
            result.reason = "yaw_too_large"
            self._reset_on_failed_frame()
            self._last_result = result
            return result
        if not (self.min_pitch_ratio <= pose.pitch_ratio <= self.max_pitch_ratio):
            result.reason = "pitch_bad"
            self._reset_on_failed_frame()
            self._last_result = result
            return result

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

        self._last_attendance_at[matched_profile.user_id] = timestamp
        result.ok = True
        result.reason = "attendance_ready"
        result.attendance_ready = True
        self._last_result = result
        return result

    def annotate_frame(self, frame_bgr: np.ndarray, result: Optional[RecognitionResult] = None) -> np.ndarray:
        """
        在图像上绘制识别结果，便于后续接摄像头页时调试。
        """

        if frame_bgr is None or frame_bgr.size == 0:
            return frame_bgr
        if result is None:
            result = self._last_result
        if result is None:
            return frame_bgr

        output = frame_bgr.copy()
        top_bar = 112
        cv2.rectangle(output, (12, 12), (438, top_bar), (9, 17, 31), -1)
        cv2.rectangle(output, (12, 12), (438, top_bar), (84, 243, 255), 1)

        title = "strict recognition"
        status = result.reason
        line2 = f"faces: {result.face_count} stable: {result.stable_count}/{result.required_count}"
        if result.recognized:
            line3 = f"{result.name} / {result.code} dist={result.distance:.3f}"
        else:
            line3 = "no confirmed identity"

        if result.location:
            top, right, bottom, left = result.location
            color = (0, 200, 0) if result.attendance_ready else ((0, 180, 255) if result.recognized else (0, 80, 255))
            cv2.rectangle(output, (left, top), (right, bottom), color, 2)
            label = result.name if result.recognized else status
            cv2.rectangle(output, (left, max(top - 26, 0)), (right, top), color, -1)
            cv2.putText(output, label[:28], (left + 6, max(top - 8, 16)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (9, 17, 31), 2)

        cv2.putText(output, title, (24, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (238, 244, 255), 2)
        cv2.putText(output, status[:40], (24, 62), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (93, 226, 165), 2)
        cv2.putText(output, line2[:50], (24, 84), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 207, 102), 1)
        cv2.putText(output, line3[:52], (24, 104), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (238, 244, 255), 1)
        return output

    def known_faces_count(self) -> int:
        return len(self.known_profiles)

    def _reset_on_failed_frame(self) -> None:
        self.reset_tracking()

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
