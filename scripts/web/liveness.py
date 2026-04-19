import time
from base64 import b64encode
from dataclasses import asdict
from dataclasses import dataclass
from threading import Lock
from typing import Optional
from uuid import uuid4

from scripts.web.registration_validation import FACE_AREA_RATIO_MIN
from scripts.web.registration_validation import PITCH_RATIO_MAX
from scripts.web.registration_validation import PITCH_RATIO_MIN
from scripts.web.registration_validation import ROLL_ANGLE_MAX
from scripts.web.registration_validation import YAW_OFFSET_MAX
from scripts.web.registration_validation import build_context
from scripts.web.registration_validation import center_point


# 这些参数统一收口，方便后续单独调优活体策略。
# 当前先偏向“更容易完成挑战”，避免移动端浏览器因为推帧和识别耗时导致频繁超时。
CHALLENGE_TTL_SECONDS = 90.0
OPEN_EAR_MIN = 0.24
CLOSED_EAR_MAX = 0.19
MIN_OPEN_FRAMES = 1
MIN_CLOSED_FRAMES = 1
MIN_REOPEN_FRAMES = 1


@dataclass
class LivenessResult:
    """
    活体挑战接口的统一返回结构。
    前端只关心状态、提示文案和是否已经拿到可信注册照。
    """

    challenge_id: str
    state: str
    passed: bool
    code: str
    message: str
    ear: Optional[float] = None
    capture_ready: bool = False
    capture_preview_data: Optional[str] = None


@dataclass
class TrustedCapture:
    """
    通过活体挑战后被冻结的最终注册照。
    提交注册时后端只接受这个对象，不再信任前端额外上传的图片。
    """

    challenge_id: str
    image_bytes: bytes
    image_type: str
    state: str


@dataclass
class BlinkChallengeSession:
    """
    一次眨眼挑战会话。
    会话内保存挑战进度和最终可信截图，避免前端伪造状态。
    """

    challenge_id: str
    expires_at: float
    state: str = "created"
    code: str = "challenge_created"
    message: str = "请正视镜头并保持自然睁眼。"
    open_frames: int = 0
    closed_frames: int = 0
    reopen_frames: int = 0
    last_ear: Optional[float] = None
    trusted_capture_bytes: Optional[bytes] = None
    trusted_capture_type: Optional[str] = None
    consumed: bool = False

    def reset_progress(self, message: str, code: str) -> None:
        """
        当检测条件被破坏时重置挑战进度。
        这样可以避免用户中途离开、换照片或多人入镜后继续沿用旧进度。
        """
        self.state = "waiting_open_eye"
        self.code = code
        self.message = message
        self.open_frames = 0
        self.closed_frames = 0
        self.reopen_frames = 0
        self.last_ear = None
        self.trusted_capture_bytes = None
        self.trusted_capture_type = None


class BlinkFrameAnalyzer:
    """
    眨眼分析器。
    它只做连续帧上的眼睛开合判断，不关心 HTTP、存储或会话管理。
    """

    def analyze(self, session: BlinkChallengeSession, image_bytes: bytes, image_type: str) -> LivenessResult:
        """
        分析单帧图像并推进眨眼状态机。
        最终可信注册照会在“闭眼后重新睁眼”的帧窗口中被冻结。
        """
        context = build_context(image_bytes)
        face_count = len(context.face_locations)

        if face_count == 0:
            session.reset_progress("未检测到清晰人脸，请正视镜头后重试。", "no_face")
            return self._result(session)
        if face_count > 1:
            session.reset_progress("检测到多张人脸，请确保单人入镜。", "multi_face")
            return self._result(session)

        if self._face_area_ratio(context) < FACE_AREA_RATIO_MIN:
            session.reset_progress("请靠近镜头一些，确保人脸足够清晰。", "face_too_small")
            return self._result(session)

        landmarks = context.face_landmarks[0] if context.face_landmarks else {}
        if not landmarks.get("left_eye") or not landmarks.get("right_eye"):
            session.reset_progress("眼部关键点提取失败，请保持正脸并避免遮挡。", "eye_landmarks_missing")
            return self._result(session)

        pose_problem = self._check_pose(landmarks)
        if pose_problem:
            session.reset_progress(pose_problem["message"], pose_problem["code"])
            return self._result(session)

        ear = self._average_ear(landmarks)
        session.last_ear = ear

        if session.state in {"created", "waiting_open_eye"}:
            self._advance_waiting_open_eye(session, ear)
            return self._result(session)

        if session.state == "waiting_blink":
            self._advance_waiting_blink(session, ear)
            return self._result(session)

        if session.state == "waiting_reopen":
            self._advance_waiting_reopen(session, ear, image_bytes, image_type)
            return self._result(session)

        if session.state == "passed":
            return self._result(session)

        session.reset_progress("请重新开始眨眼验证。", "unexpected_state")
        return self._result(session)

    def _advance_waiting_open_eye(self, session: BlinkChallengeSession, ear: float) -> None:
        """
        第一阶段先确认用户当前确实是睁眼状态。
        只有稳定睁眼之后，后面的闭眼动作才有意义。
        """
        if ear >= OPEN_EAR_MIN:
            session.open_frames += 1
        else:
            session.open_frames = 0

        if session.open_frames >= MIN_OPEN_FRAMES:
            session.state = "waiting_blink"
            session.code = "open_eye_confirmed"
            session.message = "已检测到睁眼，请自然眨眼一次。"
            return

        session.state = "waiting_open_eye"
        session.code = "waiting_open_eye"
        session.message = "请保持正脸并自然睁眼。"

    def _advance_waiting_blink(self, session: BlinkChallengeSession, ear: float) -> None:
        """
        第二阶段等待用户真正闭眼。
        这里只接受连续闭眼帧，避免单帧噪声误判成眨眼。
        """
        if ear <= CLOSED_EAR_MAX:
            session.closed_frames += 1
        else:
            session.closed_frames = 0

        if session.closed_frames >= MIN_CLOSED_FRAMES:
            session.state = "waiting_reopen"
            session.code = "blink_detected"
            session.message = "已检测到闭眼，请重新睁眼完成挑战。"
            return

        session.code = "waiting_blink"
        session.message = "请自然眨眼一次。"

    def _advance_waiting_reopen(
        self,
        session: BlinkChallengeSession,
        ear: float,
        image_bytes: bytes,
        image_type: str,
    ) -> None:
        """
        第三阶段要求用户重新睁眼。
        一旦这里通过，就直接把同一段流里的当前帧冻结成最终注册照。
        """
        if ear >= OPEN_EAR_MIN:
            session.reopen_frames += 1
            session.trusted_capture_bytes = image_bytes
            session.trusted_capture_type = image_type
        else:
            session.reopen_frames = 0

        if session.reopen_frames >= MIN_REOPEN_FRAMES:
            session.state = "passed"
            session.code = "blink_passed"
            session.message = "眨眼活体通过，已冻结最终注册照。"
            return

        session.code = "waiting_reopen"
        session.message = "检测到眨眼，请重新睁眼。"

    def _result(self, session: BlinkChallengeSession) -> LivenessResult:
        """
        把当前会话状态转换成前端可直接消费的返回结构。
        如果可信截图已经存在，就顺便带上一个预览 data URL。
        """
        preview_data = None
        if session.trusted_capture_bytes and session.trusted_capture_type:
            base64_data = b64encode(session.trusted_capture_bytes).decode("ascii")
            preview_data = f"data:image/{session.trusted_capture_type};base64,{base64_data}"

        return LivenessResult(
            challenge_id=session.challenge_id,
            state=session.state,
            passed=session.state == "passed",
            code=session.code,
            message=session.message,
            ear=session.last_ear,
            capture_ready=bool(session.trusted_capture_bytes),
            capture_preview_data=preview_data,
        )

    def _face_area_ratio(self, context) -> float:
        """
        计算人脸面积占比。
        活体挑战阶段也要拦掉脸太小的情况，否则 EAR 会非常不稳定。
        """
        top, right, bottom, left = context.face_locations[0]
        face_area = max(right - left, 0) * max(bottom - top, 0)
        image_area = max(context.width * context.height, 1)
        return face_area / image_area

    def _check_pose(self, landmarks: dict) -> Optional[dict]:
        """
        用轻量姿态门槛拦截歪头、侧脸和仰俯头。
        活体阶段先卡住姿态，能减少眨眼误检。
        """
        left_eye = center_point(landmarks["left_eye"])
        right_eye = center_point(landmarks["right_eye"])
        nose_tip = center_point(landmarks["nose_tip"])
        mouth_points = landmarks["top_lip"] + landmarks["bottom_lip"]
        mouth_center = center_point(mouth_points)

        roll_angle = abs(self._degrees(right_eye[1] - left_eye[1], right_eye[0] - left_eye[0]))
        eye_center_x = (left_eye[0] + right_eye[0]) / 2.0
        eye_distance = max(abs(right_eye[0] - left_eye[0]), 1.0)
        yaw_offset = abs(nose_tip[0] - eye_center_x) / eye_distance
        eye_center_y = (left_eye[1] + right_eye[1]) / 2.0
        vertical_span = max(abs(mouth_center[1] - eye_center_y), 1.0)
        pitch_ratio = (nose_tip[1] - eye_center_y) / vertical_span

        if roll_angle > ROLL_ANGLE_MAX:
            return {"code": "roll_too_large", "message": "请保持头部平直，不要明显歪头。"}
        if yaw_offset > YAW_OFFSET_MAX:
            return {"code": "yaw_too_large", "message": "请正视镜头，不要明显侧脸。"}
        if not (PITCH_RATIO_MIN <= pitch_ratio <= PITCH_RATIO_MAX):
            return {"code": "pitch_bad", "message": "请保持自然抬头姿态，不要低头或仰头。"}
        return None

    def _average_ear(self, landmarks: dict) -> float:
        """
        计算双眼平均 EAR。
        EAR 是眨眼检测里最常见的轻量指标，适合当前项目第一版。
        """
        left_ear = self._ear(landmarks["left_eye"])
        right_ear = self._ear(landmarks["right_eye"])
        return (left_ear + right_ear) / 2.0

    def _ear(self, points: list[tuple[int, int]]) -> float:
        """
        计算单眼 EAR。
        `face_recognition` 的眼睛关键点正好是 6 个点，适合直接套用标准公式。
        """
        if len(points) != 6:
            return 0.0

        vertical_1 = self._distance(points[1], points[5])
        vertical_2 = self._distance(points[2], points[4])
        horizontal = max(self._distance(points[0], points[3]), 1e-6)
        return (vertical_1 + vertical_2) / (2.0 * horizontal)

    def _distance(self, point_a: tuple[int, int], point_b: tuple[int, int]) -> float:
        """
        计算两点欧氏距离。
        """
        delta_x = float(point_a[0] - point_b[0])
        delta_y = float(point_a[1] - point_b[1])
        return (delta_x * delta_x + delta_y * delta_y) ** 0.5

    def _degrees(self, delta_y: float, delta_x: float) -> float:
        """
        使用反正切近似头部横向倾斜角度。
        这里只需要轻量近似，不追求 3D 头姿精度。
        """
        from math import atan2
        from math import degrees

        return degrees(atan2(delta_y, delta_x))


class LivenessChallengeService:
    """
    活体挑战服务。
    统一管理会话生命周期、状态推进和最终可信截图读取。
    """

    def __init__(self):
        self._sessions: dict[str, BlinkChallengeSession] = {}
        self._lock = Lock()
        self._analyzer = BlinkFrameAnalyzer()

    def create_challenge(self) -> LivenessResult:
        """
        创建一次新的眨眼挑战。
        """
        with self._lock:
            self._cleanup_expired_locked()
            challenge_id = uuid4().hex
            session = BlinkChallengeSession(
                challenge_id=challenge_id,
                expires_at=time.monotonic() + CHALLENGE_TTL_SECONDS,
                state="waiting_open_eye",
                code="challenge_created",
                message="请正视镜头并保持自然睁眼。",
            )
            self._sessions[challenge_id] = session
            return LivenessResult(
                challenge_id=challenge_id,
                state=session.state,
                passed=False,
                code=session.code,
                message=session.message,
            )

    def analyze_frame(self, challenge_id: str, image_bytes: bytes, image_type: str) -> LivenessResult:
        """
        推进一次挑战会话。
        如果会话不存在、已过期或已消费，会在这里直接返回明确错误。
        """
        with self._lock:
            self._cleanup_expired_locked()
            session = self._sessions.get(challenge_id)
            if not session:
                return LivenessResult(challenge_id, "expired", False, "challenge_missing", "活体挑战不存在或已过期，请重新开始。")
            if session.consumed:
                return LivenessResult(challenge_id, session.state, False, "challenge_consumed", "该挑战已经被使用，请重新开始。")
            if session.expires_at <= time.monotonic():
                session.state = "expired"
                session.code = "challenge_expired"
                session.message = "活体挑战已超时，请重新开始。"
                return self._analyzer._result(session)
            return self._analyzer.analyze(session, image_bytes, image_type)

    def get_trusted_capture(self, challenge_id: str) -> TrustedCapture:
        """
        读取已经通过活体挑战的最终注册照。
        主提交流程只能从这里拿图，不能信任前端重新上传的图片。
        """
        with self._lock:
            self._cleanup_expired_locked()
            session = self._sessions.get(challenge_id)
            if not session:
                raise ValueError("活体挑战不存在或已过期，请重新开始。")
            if session.consumed:
                raise ValueError("该活体挑战已经被使用，请重新开始。")
            if session.state != "passed":
                raise ValueError("请先完成眨眼活体挑战。")
            if not session.trusted_capture_bytes or not session.trusted_capture_type:
                raise ValueError("最终注册照尚未准备好，请重新开始挑战。")
            return TrustedCapture(
                challenge_id=challenge_id,
                image_bytes=session.trusted_capture_bytes,
                image_type=session.trusted_capture_type,
                state=session.state,
            )

    def consume_challenge(self, challenge_id: str) -> None:
        """
        成功提交注册后把挑战标记为已消费。
        这样同一段活体视频就不能重复生成多份注册记录。
        """
        with self._lock:
            session = self._sessions.get(challenge_id)
            if session:
                session.consumed = True

    def result_to_dict(self, result: LivenessResult) -> dict:
        """
        把 dataclass 结果转成 JSON 友好的字典。
        """
        return asdict(result)

    def _cleanup_expired_locked(self) -> None:
        """
        清理过期会话。
        使用内存会话时必须定期做这一步，避免无界增长。
        """
        now = time.monotonic()
        expired_ids = [
            challenge_id
            for challenge_id, session in self._sessions.items()
            if session.expires_at <= now
        ]
        for challenge_id in expired_ids:
            self._sessions.pop(challenge_id, None)
