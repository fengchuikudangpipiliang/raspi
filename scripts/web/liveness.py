import random
import time
from base64 import b64encode
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from threading import Lock
from typing import Optional
from uuid import uuid4

import face_recognition
import numpy as np

from scripts.web.registration_validation import FACE_AREA_RATIO_MIN
from scripts.web.registration_validation import PITCH_RATIO_MAX
from scripts.web.registration_validation import PITCH_RATIO_MIN
from scripts.web.registration_validation import ROLL_ANGLE_MAX
from scripts.web.registration_validation import YAW_OFFSET_MAX
from scripts.web.registration_validation import build_context
from scripts.web.registration_validation import calculate_pose_metrics
from scripts.web.registration_validation import estimate_blur_score
from scripts.web.registration_validation import extract_face_encoding
from scripts.web.registration_validation import get_primary_landmarks


# 这里统一维护注册活体挑战参数，避免路由层散落一堆硬编码。
# 当前策略刻意偏向“低流量 + 树莓派可落地”，不再依赖连续送帧抓眨眼。
CHALLENGE_TTL_SECONDS = 180.0
# 第一轮动作挑战实测发现“左右转头”门槛过高时，用户很容易在手机和普通 USB 摄像头下反复失败。
# 这里把正脸和侧转的区间拉宽到更贴近真实使用的范围，让“轻微侧转”也能通过。
FRONT_YAW_MAX = 0.18
SIDE_YAW_MIN = 0.12
SIDE_YAW_MAX = 0.60
FACE_ENCODING_DISTANCE_MAX = 0.42

# 注册端采用固定 3 步动作挑战：
# 第一步要求正脸，第二步随机要求左右转头其一，第三步再回正脸。
# 这样既能验证动作变化，也能在最后拿到更适合入库的正脸注册照。
ACTION_TEMPLATES: tuple[tuple[str, ...], ...] = (
    ("front", "left", "front"),
    ("front", "right", "front"),
)

STEP_COPY = {
    "front": {
        "title": "正视镜头",
        "instruction": "请保持正脸，眼睛看向镜头中央后拍摄当前步骤。",
    },
    "left": {
        "title": "向左转头",
        "instruction": "请把头轻微转向你的左侧，露出一点侧脸后拍摄当前步骤。",
    },
    "right": {
        "title": "向右转头",
        "instruction": "请把头轻微转向你的右侧，露出一点侧脸后拍摄当前步骤。",
    },
}


@dataclass
class ChallengeStep:
    """
    单个动作挑战步骤定义。
    它只描述“当前要做什么动作”，不保存会话状态。
    """

    key: str
    title: str
    instruction: str


@dataclass
class StepProgress:
    """
    前端展示用的步骤进度结构。
    每次提交抓拍后，后端都会返回整条挑战的最新进度。
    """

    index: int
    key: str
    title: str
    instruction: str
    status: str


@dataclass
class LivenessResult:
    """
    动作挑战接口统一返回结构。
    前端只消费挑战状态、当前步骤和是否已经拿到可信注册照。
    """

    challenge_id: str
    state: str
    passed: bool
    code: str
    message: str
    current_step_index: int
    total_steps: int
    current_step_key: Optional[str]
    current_step_title: Optional[str]
    current_step_instruction: Optional[str]
    steps: list[StepProgress]
    capture_ready: bool = False
    capture_preview_data: Optional[str] = None
    signed_yaw: Optional[float] = None
    yaw_offset: Optional[float] = None
    roll_angle: Optional[float] = None


@dataclass
class TrustedCapture:
    """
    通过动作挑战后冻结的最终注册照。
    正式提交时后端只接受这个对象，不再信任前端自由上传最终图片。
    """

    challenge_id: str
    image_bytes: bytes
    image_type: str
    state: str
    steps_payload: list[dict]


@dataclass
class AcceptedCapture:
    """
    一次已经通过动作校验的抓拍结果。
    会话里保存它，便于后续做同人一致性比对和最佳注册照挑选。
    """

    step_key: str
    image_bytes: bytes
    image_type: str
    blur_score: float
    encoding: np.ndarray


@dataclass
class ActionChallengeSession:
    """
    一次动作活体挑战会话。
    会话内保存挑战步骤、已通过步骤和最终可信注册照，避免前端伪造状态。
    """

    challenge_id: str
    expires_at: float
    steps: list[ChallengeStep]
    state: str = "waiting_capture"
    code: str = "challenge_created"
    message: str = "请先完成第 1 步：正视镜头。"
    current_step_index: int = 0
    accepted_captures: list[AcceptedCapture] = field(default_factory=list)
    trusted_capture_bytes: Optional[bytes] = None
    trusted_capture_type: Optional[str] = None
    consumed: bool = False
    last_signed_yaw: Optional[float] = None
    last_yaw_offset: Optional[float] = None
    last_roll_angle: Optional[float] = None

    def current_step(self) -> Optional[ChallengeStep]:
        """
        返回当前仍待完成的步骤。
        如果已经全部完成，就返回 None。
        """
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None


class ActionChallengeAnalyzer:
    """
    分步动作挑战分析器。
    它只关心“这张抓拍图是否满足当前动作步骤”，不关心 HTTP 和会话存储。
    """

    def analyze_capture(self, session: ActionChallengeSession, image_bytes: bytes, image_type: str) -> LivenessResult:
        """
        分析当前抓拍图并推进挑战步骤。
        每次调用只处理一张图片，因此天然是低流量模式。
        """
        try:
            context = build_context(image_bytes)
        except ValueError as error:
            session.code = "image_decode_failed"
            session.message = str(error)
            return self._result(session)

        face_count = len(context.face_locations)
        if face_count == 0:
            session.code = "no_face"
            session.message = "未检测到清晰人脸，请调整姿势后重新抓拍。"
            return self._result(session)
        if face_count > 1:
            session.code = "multi_face"
            session.message = "检测到多张人脸，请确保单人入镜后重新抓拍。"
            return self._result(session)

        if self._face_area_ratio(context) < FACE_AREA_RATIO_MIN:
            session.code = "face_too_small"
            session.message = "请靠近镜头一些，确保人脸足够清晰后再抓拍。"
            return self._result(session)

        try:
            landmarks = get_primary_landmarks(context)
        except ValueError as error:
            session.code = "landmarks_missing"
            session.message = str(error)
            return self._result(session)

        pose_metrics = calculate_pose_metrics(landmarks)
        session.last_signed_yaw = pose_metrics.signed_yaw
        session.last_yaw_offset = pose_metrics.yaw_offset
        session.last_roll_angle = pose_metrics.roll_angle

        current_step = session.current_step()
        if current_step is None:
            session.code = "challenge_already_passed"
            session.message = "动作挑战已完成，请直接提交资料。"
            return self._result(session)

        step_problem = self._check_step_pose(current_step.key, pose_metrics)
        if step_problem:
            session.code = step_problem["code"]
            session.message = step_problem["message"]
            return self._result(session)

        try:
            encoding = extract_face_encoding(context)
        except ValueError as error:
            session.code = "face_encoding_failed"
            session.message = str(error)
            return self._result(session)

        identity_problem = self._check_same_person(session, encoding)
        if identity_problem:
            session.code = identity_problem["code"]
            session.message = identity_problem["message"]
            return self._result(session)

        accepted_capture = AcceptedCapture(
            step_key=current_step.key,
            image_bytes=image_bytes,
            image_type=image_type,
            blur_score=estimate_blur_score(context),
            encoding=encoding,
        )
        session.accepted_captures.append(accepted_capture)
        session.current_step_index += 1

        if session.current_step_index >= len(session.steps):
            trusted_capture = self._select_trusted_capture(session)
            session.trusted_capture_bytes = trusted_capture.image_bytes
            session.trusted_capture_type = trusted_capture.image_type
            session.state = "passed"
            session.code = "challenge_passed"
            session.message = "动作活体挑战已通过，已冻结可信注册照。"
            return self._result(session)

        next_step = session.current_step()
        session.state = "waiting_capture"
        session.code = "step_passed"
        session.message = f"当前步骤已通过，请继续第 {session.current_step_index + 1} 步：{next_step.title}。"
        return self._result(session)

    def _check_step_pose(self, step_key: str, pose_metrics) -> Optional[dict]:
        """
        校验当前抓拍是否满足指定动作步骤。
        这里只做轻量姿态规则，优先保证在树莓派和公网链路上可跑通。
        """
        if pose_metrics.roll_angle > ROLL_ANGLE_MAX:
            return {"code": "roll_too_large", "message": "请保持头部平直，不要明显歪头后再抓拍。"}
        if not (PITCH_RATIO_MIN <= pose_metrics.pitch_ratio <= PITCH_RATIO_MAX):
            return {"code": "pitch_bad", "message": "请保持自然抬头姿态，不要低头或仰头后再抓拍。"}

        if step_key == "front":
            if pose_metrics.yaw_offset > FRONT_YAW_MAX:
                return {"code": "front_pose_required", "message": "当前步骤需要正脸，请把脸转回镜头中央后重试。"}
            return None

        if step_key == "left":
            if pose_metrics.signed_yaw >= -SIDE_YAW_MIN:
                return {"code": "left_pose_required", "message": "当前步骤需要轻微向左转头，露出一点侧脸后再抓拍。"}
            if abs(pose_metrics.signed_yaw) > SIDE_YAW_MAX:
                return {"code": "left_pose_too_large", "message": "头转得太多了，请稍微回正一点，只保留轻微侧转后再抓拍。"}
            return None

        if step_key == "right":
            if pose_metrics.signed_yaw <= SIDE_YAW_MIN:
                return {"code": "right_pose_required", "message": "当前步骤需要轻微向右转头，露出一点侧脸后再抓拍。"}
            if abs(pose_metrics.signed_yaw) > SIDE_YAW_MAX:
                return {"code": "right_pose_too_large", "message": "头转得太多了，请稍微回正一点，只保留轻微侧转后再抓拍。"}
            return None

        return {"code": "unknown_step", "message": "当前动作步骤异常，请重新开始挑战。"}

    def _check_same_person(self, session: ActionChallengeSession, encoding: np.ndarray) -> Optional[dict]:
        """
        校验当前抓拍和前面已通过的步骤是否来自同一个人。
        这样可以防止中途换人继续完成挑战。
        """
        if not session.accepted_captures:
            return None

        reference_encoding = session.accepted_captures[0].encoding
        distance = float(face_recognition.face_distance([reference_encoding], encoding)[0])
        if distance <= FACE_ENCODING_DISTANCE_MAX:
            return None
        return {
            "code": "identity_changed",
            "message": "当前抓拍和前一步不是同一个人，请由同一位用户继续完成挑战。",
        }

    def _select_trusted_capture(self, session: ActionChallengeSession) -> AcceptedCapture:
        """
        从已通过步骤里挑出最终可信注册照。
        当前优先选择正脸步骤里最清晰的一张，保证后续编码质量更稳定。
        """
        front_candidates = [
            capture
            for capture in session.accepted_captures
            if capture.step_key == "front"
        ]
        candidates = front_candidates or session.accepted_captures
        return max(candidates, key=lambda capture: capture.blur_score)

    def _result(self, session: ActionChallengeSession) -> LivenessResult:
        """
        把当前会话状态转换成前端可直接消费的返回结构。
        如果可信注册照已经存在，会顺便附带预览 data URL。
        """
        preview_data = None
        if session.trusted_capture_bytes and session.trusted_capture_type:
            base64_data = b64encode(session.trusted_capture_bytes).decode("ascii")
            preview_data = f"data:image/{session.trusted_capture_type};base64,{base64_data}"

        current_step = session.current_step()
        steps = self._build_steps_progress(session)
        return LivenessResult(
            challenge_id=session.challenge_id,
            state=session.state,
            passed=session.state == "passed",
            code=session.code,
            message=session.message,
            current_step_index=session.current_step_index,
            total_steps=len(session.steps),
            current_step_key=current_step.key if current_step else None,
            current_step_title=current_step.title if current_step else None,
            current_step_instruction=current_step.instruction if current_step else None,
            steps=steps,
            capture_ready=bool(session.trusted_capture_bytes),
            capture_preview_data=preview_data,
            signed_yaw=session.last_signed_yaw,
            yaw_offset=session.last_yaw_offset,
            roll_angle=session.last_roll_angle,
        )

    def _build_steps_progress(self, session: ActionChallengeSession) -> list[StepProgress]:
        """
        基于当前步骤索引，构造前端展示用的步骤进度条数据。
        """
        progress: list[StepProgress] = []
        for index, step in enumerate(session.steps):
            status = "pending"
            if index < session.current_step_index:
                status = "completed"
            elif index == session.current_step_index and session.state != "passed":
                status = "active"
            progress.append(
                StepProgress(
                    index=index + 1,
                    key=step.key,
                    title=step.title,
                    instruction=step.instruction,
                    status=status,
                )
            )
        return progress

    def _face_area_ratio(self, context) -> float:
        """
        计算人脸面积占比。
        分步动作挑战也要拦掉脸太小的情况，否则姿态判断会非常不稳定。
        """
        top, right, bottom, left = context.face_locations[0]
        face_area = max(right - left, 0) * max(bottom - top, 0)
        image_area = max(context.width * context.height, 1)
        return face_area / image_area


class LivenessChallengeService:
    """
    动作挑战服务。
    统一管理会话生命周期、状态推进和最终可信截图读取。
    """

    def __init__(self):
        self._sessions: dict[str, ActionChallengeSession] = {}
        self._lock = Lock()
        self._analyzer = ActionChallengeAnalyzer()

    def create_challenge(self) -> LivenessResult:
        """
        创建一次新的动作挑战。
        挑战步骤会从预设模板里随机选择一套，避免所有用户都走同一条固定路径。
        """
        with self._lock:
            self._cleanup_expired_locked()
            challenge_id = uuid4().hex
            steps = self._build_random_steps()
            session = ActionChallengeSession(
                challenge_id=challenge_id,
                expires_at=time.monotonic() + CHALLENGE_TTL_SECONDS,
                steps=steps,
                state="waiting_capture",
                code="challenge_created",
                message=f"动作挑战已创建，请先完成第 1 步：{steps[0].title}。",
            )
            self._sessions[challenge_id] = session
            return self._analyzer._result(session)

    def analyze_capture(self, challenge_id: str, image_bytes: bytes, image_type: str) -> LivenessResult:
        """
        推进一次动作挑战会话。
        如果会话不存在、已过期或已消费，会在这里直接返回明确错误。
        """
        with self._lock:
            self._cleanup_expired_locked()
            session = self._sessions.get(challenge_id)
            if not session:
                return self._error_result(challenge_id, "expired", "challenge_missing", "动作挑战不存在或已过期，请重新开始。")
            if session.consumed:
                return self._error_result(challenge_id, session.state, "challenge_consumed", "该动作挑战已经被使用，请重新开始。")
            if session.expires_at <= time.monotonic():
                session.state = "expired"
                session.code = "challenge_expired"
                session.message = "动作挑战已超时，请重新开始。"
                return self._analyzer._result(session)
            return self._analyzer.analyze_capture(session, image_bytes, image_type)

    def get_trusted_capture(self, challenge_id: str) -> TrustedCapture:
        """
        读取已经通过动作挑战的最终注册照。
        主提交流程只能从这里拿图，不能信任前端重新上传的图片。
        """
        with self._lock:
            self._cleanup_expired_locked()
            session = self._sessions.get(challenge_id)
            if not session:
                raise ValueError("动作挑战不存在或已过期，请重新开始。")
            if session.consumed:
                raise ValueError("该动作挑战已经被使用，请重新开始。")
            if session.state != "passed":
                raise ValueError("请先完成动作活体挑战。")
            if not session.trusted_capture_bytes or not session.trusted_capture_type:
                raise ValueError("最终注册照尚未准备好，请重新开始挑战。")
            return TrustedCapture(
                challenge_id=challenge_id,
                image_bytes=session.trusted_capture_bytes,
                image_type=session.trusted_capture_type,
                state=session.state,
                steps_payload=[asdict(step) for step in self._analyzer._build_steps_progress(session)],
            )

    def consume_challenge(self, challenge_id: str) -> None:
        """
        成功提交注册后把挑战标记为已消费。
        这样同一组动作抓拍就不能重复生成多份注册记录。
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

    def _build_random_steps(self) -> list[ChallengeStep]:
        """
        生成一组随机动作步骤。
        模板是固定离线配置，不依赖任何在线模型下载。
        """
        template = random.choice(ACTION_TEMPLATES)
        return [
            ChallengeStep(
                key=step_key,
                title=STEP_COPY[step_key]["title"],
                instruction=STEP_COPY[step_key]["instruction"],
            )
            for step_key in template
        ]

    def _error_result(self, challenge_id: str, state: str, code: str, message: str) -> LivenessResult:
        """
        构造会话缺失、已消费等错误场景的统一返回体。
        """
        return LivenessResult(
            challenge_id=challenge_id,
            state=state,
            passed=False,
            code=code,
            message=message,
            current_step_index=0,
            total_steps=0,
            current_step_key=None,
            current_step_title=None,
            current_step_instruction=None,
            steps=[],
        )

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
