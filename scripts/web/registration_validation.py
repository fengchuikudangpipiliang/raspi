from dataclasses import asdict
from dataclasses import dataclass
from math import atan2
from typing import Optional

import cv2
import face_recognition
import numpy as np


# 这些阈值统一收口，后续调参时只需要改这一处。
#解释下面参数
FACE_AREA_RATIO_MIN = 0.08 #
LAPLACIAN_VARIANCE_MIN = 110.0
BRIGHTNESS_MEAN_MIN = 65.0
BRIGHTNESS_MEAN_MAX = 195.0
ROLL_ANGLE_MAX = 12.0
YAW_OFFSET_MAX = 0.18
PITCH_RATIO_MIN = 0.32
PITCH_RATIO_MAX = 0.78
PRESENTATION_RECT_AREA_MIN_RATIO = 0.10
PRESENTATION_PERIODIC_RATIO_MIN = 9.5
PRESENTATION_GLARE_RATIO_MIN = 0.03
DETECTION_MAX_WIDTH = 480


@dataclass
class ValidationResult:
    """
    统一的校验结果结构。
    每个校验器都返回这个结构，方便前后端用统一格式处理。
    """

    name: str
    passed: bool
    code: str
    message: str
    score: Optional[float] = None
    threshold: Optional[float] = None


@dataclass
class ValidationContext:
    """
    校验上下文。
    中间产物统一缓存到这里，避免每个校验器都重复做人脸检测和关键点提取。
    """

    image_bytes: bytes
    image_bgr: np.ndarray
    image_rgb: np.ndarray
    width: int
    height: int
    face_locations: list[tuple[int, int, int, int]]
    face_landmarks: list[dict]


@dataclass
class PoseMetrics:
    """
    轻量姿态估计结果。
    这里把注册校验和动作活体都需要的姿态中间量统一收口，避免两边各算一遍。
    """

    roll_angle: float
    yaw_offset: float
    signed_yaw: float
    pitch_ratio: float


class BaseValidator:
    """
    所有校验器的抽象基类。
    每个子类只负责一种校验能力，符合高内聚低耦合设计。
    """

    name = "base"

    def validate(self, context: ValidationContext) -> ValidationResult:
        raise NotImplementedError


class FaceCountValidator(BaseValidator):
    """
    检查图片中是否只存在一张脸。
    这是注册链路最前面的硬门槛。
    """

    name = "face_count"

    def validate(self, context: ValidationContext) -> ValidationResult:
        count = len(context.face_locations)
        if count == 1:
            return ValidationResult(self.name, True, "face_count_ok", "检测到 1 张人脸。", float(count), 1.0)
        if count == 0:
            return ValidationResult(self.name, False, "no_face", "未检测到清晰人脸，请重新拍摄。", float(count), 1.0)
        return ValidationResult(self.name, False, "multi_face", "检测到多张人脸，请确保单人入镜。", float(count), 1.0)


class FaceSizeValidator(BaseValidator):
    """
    检查人脸区域在整张图片中的占比。
    人脸太小会显著影响后续特征提取质量。
    """

    name = "face_size"

    def validate(self, context: ValidationContext) -> ValidationResult:
        top, right, bottom, left = context.face_locations[0]
        face_area = max(right - left, 0) * max(bottom - top, 0)
        image_area = context.width * context.height
        ratio = face_area / image_area if image_area else 0.0

        if ratio >= FACE_AREA_RATIO_MIN:
            return ValidationResult(self.name, True, "face_size_ok", "人脸尺寸合格。", ratio, FACE_AREA_RATIO_MIN)
        return ValidationResult(
            self.name,
            False,
            "face_too_small",
            "人脸区域太小，请靠近镜头并保持正脸。",
            ratio,
            FACE_AREA_RATIO_MIN,
        )


class BlurValidator(BaseValidator):
    """
    用 Laplacian 方差做模糊检测。
    这是轻量且常用的清晰度判断方法，适合树莓派项目第一版。
    """

    name = "blur"

    def validate(self, context: ValidationContext) -> ValidationResult:
        roi = extract_face_roi(context)
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        score = float(cv2.Laplacian(gray, cv2.CV_64F).var())

        if score >= LAPLACIAN_VARIANCE_MIN:
            return ValidationResult(self.name, True, "blur_ok", "照片清晰度合格。", score, LAPLACIAN_VARIANCE_MIN)
        return ValidationResult(self.name, False, "image_blurry", "照片过于模糊，请重新拍摄。", score, LAPLACIAN_VARIANCE_MIN)


class BrightnessValidator(BaseValidator):
    """
    用脸部区域灰度均值做亮度检查。
    先实现一个可解释且足够稳定的轻量版本。
    """

    name = "brightness"

    def validate(self, context: ValidationContext) -> ValidationResult:
        roi = extract_face_roi(context)
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        score = float(gray.mean())

        if BRIGHTNESS_MEAN_MIN <= score <= BRIGHTNESS_MEAN_MAX:
            return ValidationResult(self.name, True, "brightness_ok", "照片亮度合格。", score, BRIGHTNESS_MEAN_MIN)
        return ValidationResult(
            self.name,
            False,
            "bad_lighting",
            "光线条件不理想，请避免过暗、过亮或强逆光。",
            score,
            BRIGHTNESS_MEAN_MIN,
        )


class LandmarkIntegrityValidator(BaseValidator):
    """
    检查关键五官区域是否都能稳定提取。
    缺失常常意味着遮挡严重或图像质量太差。
    """

    name = "landmarks"
    required_keys = ("left_eye", "right_eye", "nose_tip", "top_lip", "bottom_lip")

    def validate(self, context: ValidationContext) -> ValidationResult:
        if not context.face_landmarks:
            return ValidationResult(self.name, False, "landmarks_missing", "关键点提取失败，请重新拍摄。")

        landmarks = context.face_landmarks[0]
        missing = [key for key in self.required_keys if not landmarks.get(key)]
        if not missing:
            return ValidationResult(self.name, True, "landmarks_ok", "五官关键点提取正常。")

        return ValidationResult(
            self.name,
            False,
            "landmarks_incomplete",
            f"关键点不完整，疑似遮挡或姿态异常：{', '.join(missing)}。",
        )


class PoseValidator(BaseValidator):
    """
    用关键点做一个轻量姿态估计。
    目标不是高精度 3D 头姿，而是拦截明显歪头、侧脸、低头和仰头。
    """

    name = "pose"

    def validate(self, context: ValidationContext) -> ValidationResult:
        pose_metrics = calculate_pose_metrics(get_primary_landmarks(context))

        if pose_metrics.roll_angle > ROLL_ANGLE_MAX:
            return ValidationResult(self.name, False, "roll_too_large", "请保持头部平直，不要明显歪头。", pose_metrics.roll_angle, ROLL_ANGLE_MAX)
        if pose_metrics.yaw_offset > YAW_OFFSET_MAX:
            return ValidationResult(self.name, False, "yaw_too_large", "请正视镜头，不要明显侧脸。", pose_metrics.yaw_offset, YAW_OFFSET_MAX)
        if not (PITCH_RATIO_MIN <= pose_metrics.pitch_ratio <= PITCH_RATIO_MAX):
            return ValidationResult(self.name, False, "pitch_bad", "请保持自然抬头姿态，不要低头或仰头。", pose_metrics.pitch_ratio, PITCH_RATIO_MIN)
        return ValidationResult(self.name, True, "pose_ok", "人脸姿态合格。", pose_metrics.yaw_offset, YAW_OFFSET_MAX)


class PresentationAttackValidator(BaseValidator):
    """
    轻量翻拍检测校验器。
    目标不是商用级活体，而是在不引入在线模型的前提下，尽量拦截纸张和屏幕翻拍。
    """

    name = "presentation_attack"

    def validate(self, context: ValidationContext) -> ValidationResult:
        signals = estimate_presentation_attack_signals(context)
        suspicious_count = 0
        reasons: list[str] = []

        if signals["rectangular_frame_detected"]:
            suspicious_count += 1
            reasons.append("检测到包裹人脸的矩形边框")
        if signals["periodic_artifact_score"] >= PRESENTATION_PERIODIC_RATIO_MIN:
            suspicious_count += 1
            reasons.append("检测到疑似屏幕/印刷周期纹理")
        if signals["glare_ratio"] >= PRESENTATION_GLARE_RATIO_MIN:
            suspicious_count += 1
            reasons.append("检测到疑似屏幕反光高亮")

        high_confidence = signals["rectangular_frame_detected"] and suspicious_count >= 2
        if high_confidence or suspicious_count >= 2:
            message = "疑似纸张或屏幕翻拍，请让本人直接面对摄像头重新采集。"
            if reasons:
                message = f"{message} 命中信号：{'、'.join(reasons)}。"
            return ValidationResult(
                self.name,
                False,
                "presentation_attack_suspected",
                message,
                float(suspicious_count),
                2.0,
            )

        return ValidationResult(
            self.name,
            True,
            "presentation_attack_clear",
            "未检测到明显纸张或屏幕翻拍特征。",
            float(suspicious_count),
            2.0,
        )


class RegistrationValidationPipeline:
    """
    注册校验流水线。
    主流程只负责串联校验器，新增规则时只新增类并挂到列表里即可。
    """

    def __init__(self):
        self.validators: list[BaseValidator] = [
            FaceCountValidator(),
            FaceSizeValidator(),
            BlurValidator(),
            BrightnessValidator(),
            LandmarkIntegrityValidator(),
            PoseValidator(),
            PresentationAttackValidator(),
        ]

    def validate(self, image_bytes: bytes) -> tuple[bool, list[ValidationResult]]:
        _, passed, results = self.validate_with_context(image_bytes)
        return passed, results

    def validate_with_context(self, image_bytes: bytes) -> tuple[ValidationContext, bool, list[ValidationResult]]:
        context = build_context(image_bytes)
        results: list[ValidationResult] = []

        for validator in self.validators:
            result = validator.validate(context)
            results.append(result)
            if not result.passed and validator.name == "face_count":
                break

        return context, all(result.passed for result in results), results


def build_context(image_bytes: bytes) -> ValidationContext:
    """
    从原始图片字节构建统一上下文。
    图片解码、人脸检测、关键点提取都在这里一次性完成。
    """
    np_buffer = np.frombuffer(image_bytes, dtype=np.uint8)
    image_bgr = cv2.imdecode(np_buffer, cv2.IMREAD_COLOR)
    if image_bgr is None or image_bgr.size == 0:
        raise ValueError("图片解码失败，请重新上传。")

    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    height, width = image_bgr.shape[:2]
    detect_rgb = image_rgb
    detect_scale = 1.0
    if width > DETECTION_MAX_WIDTH:
        detect_scale = DETECTION_MAX_WIDTH / float(width)
        detect_width = max(1, int(width * detect_scale))
        detect_height = max(1, int(height * detect_scale))
        detect_rgb = cv2.resize(
            image_rgb,
            (detect_width, detect_height),
            interpolation=cv2.INTER_AREA,
        )

    detected_locations = face_recognition.face_locations(detect_rgb, model="hog")
    if detect_scale != 1.0:
        face_locations = [
            (
                int(round(top / detect_scale)),
                int(round(right / detect_scale)),
                int(round(bottom / detect_scale)),
                int(round(left / detect_scale)),
            )
            for top, right, bottom, left in detected_locations
        ]
    else:
        face_locations = detected_locations
    face_landmarks = face_recognition.face_landmarks(image_rgb, face_locations) if face_locations else []
    return ValidationContext(image_bytes, image_bgr, image_rgb, width, height, face_locations, face_landmarks)


def extract_face_roi(context: ValidationContext) -> np.ndarray:
    """
    裁剪第一张脸的人脸区域。
    所有需要分析脸部图像质量的校验器都复用这个函数。
    """
    top, right, bottom, left = context.face_locations[0]
    margin_x = int((right - left) * 0.08)
    margin_y = int((bottom - top) * 0.08)

    top = max(top - margin_y, 0)
    bottom = min(bottom + margin_y, context.height)
    left = max(left - margin_x, 0)
    right = min(right + margin_x, context.width)
    return context.image_bgr[top:bottom, left:right]


def get_primary_landmarks(context: ValidationContext) -> dict:
    """
    返回第一张脸的关键点集合。
    注册校验、动作活体和后续识别辅助逻辑都可以复用这一步。
    """
    if not context.face_landmarks:
        raise ValueError("关键点提取失败，请保持正脸并避免遮挡。")

    landmarks = context.face_landmarks[0]
    required_keys = ("left_eye", "right_eye", "nose_tip", "top_lip", "bottom_lip")
    missing = [key for key in required_keys if not landmarks.get(key)]
    if missing:
        raise ValueError(f"关键点不完整，疑似遮挡或姿态异常：{', '.join(missing)}。")
    return landmarks


def calculate_pose_metrics(landmarks: dict) -> PoseMetrics:
    """
    基于关键点做轻量姿态估计。
    这里保留 signed_yaw，方便动作挑战区分“向左转头”和“向右转头”。
    """
    left_eye = center_point(landmarks["left_eye"])
    right_eye = center_point(landmarks["right_eye"])
    nose_tip = center_point(landmarks["nose_tip"])
    mouth_points = landmarks["top_lip"] + landmarks["bottom_lip"]
    mouth_center = center_point(mouth_points)

    roll_angle = abs(np.degrees(atan2(right_eye[1] - left_eye[1], right_eye[0] - left_eye[0])))
    eye_center_x = (left_eye[0] + right_eye[0]) / 2.0
    eye_distance = max(abs(right_eye[0] - left_eye[0]), 1.0)
    signed_yaw = (nose_tip[0] - eye_center_x) / eye_distance
    yaw_offset = abs(signed_yaw)
    eye_center_y = (left_eye[1] + right_eye[1]) / 2.0
    vertical_span = max(abs(mouth_center[1] - eye_center_y), 1.0)
    pitch_ratio = (nose_tip[1] - eye_center_y) / vertical_span
    return PoseMetrics(
        roll_angle=roll_angle,
        yaw_offset=yaw_offset,
        signed_yaw=signed_yaw,
        pitch_ratio=pitch_ratio,
    )


def estimate_blur_score(context: ValidationContext) -> float:
    """
    返回脸部 ROI 的 Laplacian 清晰度分数。
    动作挑战在挑选最终注册照时会优先选择更清晰的正脸抓拍。
    """
    roi = extract_face_roi(context)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def extract_face_encoding(context: ValidationContext) -> np.ndarray:
    """
    提取第一张脸的人脸编码。
    如果编码失败，会抛出明确错误供上层统一处理。
    """
    encodings = face_recognition.face_encodings(
        context.image_rgb,
        known_face_locations=context.face_locations,
        num_jitters=1,
        model="small",
    )
    if not encodings:
        raise ValueError("人脸特征提取失败，请重新拍摄清晰正脸照片。")
    return encodings[0]


def estimate_presentation_attack_signals(context: ValidationContext) -> dict:
    """
    估计纸张/屏幕翻拍相关信号。
    这里采用多信号轻量策略：矩形边框、周期纹理和强反光。
    单个信号不足以判死刑，组合命中时才判为可疑，尽量减少误杀。
    """
    roi = extract_face_roi(context)
    return {
        "rectangular_frame_detected": detect_face_enclosing_rectangle(context),
        "periodic_artifact_score": estimate_periodic_artifact_score(roi),
        "glare_ratio": estimate_glare_ratio(roi),
    }


def detect_face_enclosing_rectangle(context: ValidationContext) -> bool:
    """
    检测人脸外是否存在包裹式的大矩形边框。
    这是手机屏幕边框、纸张边缘最常见的离线特征之一。
    """
    gray = cv2.cvtColor(context.image_bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 60, 160)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    top, right, bottom, left = context.face_locations[0]
    face_width = max(right - left, 1)
    face_height = max(bottom - top, 1)
    image_area = max(context.width * context.height, 1)

    for contour in contours:
        area = cv2.contourArea(contour)
        if area < image_area * PRESENTATION_RECT_AREA_MIN_RATIO:
            continue

        perimeter = cv2.arcLength(contour, True)
        if perimeter <= 0:
            continue

        polygon = cv2.approxPolyDP(contour, 0.03 * perimeter, True)
        if len(polygon) < 4 or len(polygon) > 6:
            continue

        x, y, width, height = cv2.boundingRect(polygon)
        if width <= 0 or height <= 0:
            continue

        # 只关心和脸大小相近、又不是整张画面边界的矩形，避免把背景里的门框或取景边缘误判进去。
        if width < face_width * 1.05 or height < face_height * 1.05:
            continue
        if width > face_width * 3.2 or height > face_height * 3.6:
            continue
        if x <= context.width * 0.02 or y <= context.height * 0.02:
            continue
        if x + width >= context.width * 0.98 or y + height >= context.height * 0.98:
            continue

        if x > left or y > top or x + width < right or y + height < bottom:
            continue

        rectangularity = area / max(width * height, 1)
        if rectangularity < 0.72:
            continue
        return True

    return False


def estimate_periodic_artifact_score(roi: np.ndarray) -> float:
    """
    估计 ROI 中疑似屏幕像素栅格或纸张印刷纹理带来的周期性条纹强度。
    分数越高，越像“二次翻拍后出现的规律纹理”。
    """
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    normalized = cv2.resize(gray, (160, 160), interpolation=cv2.INTER_AREA)

    horizontal_profile = np.abs(cv2.Sobel(normalized, cv2.CV_32F, 1, 0, ksize=3)).mean(axis=0)
    vertical_profile = np.abs(cv2.Sobel(normalized, cv2.CV_32F, 0, 1, ksize=3)).mean(axis=1)
    return max(
        estimate_profile_periodicity(horizontal_profile),
        estimate_profile_periodicity(vertical_profile),
    )


def estimate_profile_periodicity(profile: np.ndarray) -> float:
    """
    估计一维梯度剖面的周期峰值强度。
    如果图像里存在明显规律纹理，频域里会出现更突出的峰值。
    """
    profile = np.asarray(profile, dtype=np.float32)
    if profile.size < 32:
        return 0.0

    profile = profile - float(profile.mean())
    spectrum = np.abs(np.fft.rfft(profile))
    if spectrum.size <= 4:
        return 0.0

    useful = spectrum[3:]
    if not useful.size:
        return 0.0

    mean_energy = float(useful.mean())
    if mean_energy <= 1e-6:
        return 0.0
    return float(useful.max() / mean_energy)


def estimate_glare_ratio(roi: np.ndarray) -> float:
    """
    估计脸部 ROI 中的高亮低饱和区域占比。
    手机屏幕翻拍常见的反光高亮通常会落在这类区域里。
    """
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    highlight_mask = (hsv[:, :, 2] >= 242) & (hsv[:, :, 1] <= 42)
    return float(highlight_mask.mean())


def center_point(points: list[tuple[int, int]]) -> tuple[float, float]:
    """
    计算一组关键点的中心点。
    用于轻量姿态估计。
    """
    x = sum(point[0] for point in points) / len(points)
    y = sum(point[1] for point in points) / len(points)
    return x, y


def results_to_dicts(results: list[ValidationResult]) -> list[dict]:
    """
    把 dataclass 结果转成可直接 JSON 序列化的结构。
    """
    return [asdict(result) for result in results]
