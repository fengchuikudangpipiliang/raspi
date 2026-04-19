from dataclasses import asdict
from dataclasses import dataclass
from math import atan2
from typing import Optional

import cv2
import face_recognition
import numpy as np


# 这些阈值统一收口，后续调参时只需要改这一处。
FACE_AREA_RATIO_MIN = 0.08
LAPLACIAN_VARIANCE_MIN = 110.0
BRIGHTNESS_MEAN_MIN = 65.0
BRIGHTNESS_MEAN_MAX = 195.0
ROLL_ANGLE_MAX = 12.0
YAW_OFFSET_MAX = 0.18
PITCH_RATIO_MIN = 0.32
PITCH_RATIO_MAX = 0.78


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
        landmarks = context.face_landmarks[0]
        left_eye = center_point(landmarks["left_eye"])
        right_eye = center_point(landmarks["right_eye"])
        nose_tip = center_point(landmarks["nose_tip"])
        mouth_points = landmarks["top_lip"] + landmarks["bottom_lip"]
        mouth_center = center_point(mouth_points)

        roll_angle = abs(np.degrees(atan2(right_eye[1] - left_eye[1], right_eye[0] - left_eye[0])))
        eye_center_x = (left_eye[0] + right_eye[0]) / 2.0
        eye_distance = max(abs(right_eye[0] - left_eye[0]), 1.0)
        yaw_offset = abs(nose_tip[0] - eye_center_x) / eye_distance
        eye_center_y = (left_eye[1] + right_eye[1]) / 2.0
        vertical_span = max(abs(mouth_center[1] - eye_center_y), 1.0)
        pitch_ratio = (nose_tip[1] - eye_center_y) / vertical_span

        if roll_angle > ROLL_ANGLE_MAX:
            return ValidationResult(self.name, False, "roll_too_large", "请保持头部平直，不要明显歪头。", roll_angle, ROLL_ANGLE_MAX)
        if yaw_offset > YAW_OFFSET_MAX:
            return ValidationResult(self.name, False, "yaw_too_large", "请正视镜头，不要明显侧脸。", yaw_offset, YAW_OFFSET_MAX)
        if not (PITCH_RATIO_MIN <= pitch_ratio <= PITCH_RATIO_MAX):
            return ValidationResult(self.name, False, "pitch_bad", "请保持自然抬头姿态，不要低头或仰头。", pitch_ratio, PITCH_RATIO_MIN)
        return ValidationResult(self.name, True, "pose_ok", "人脸姿态合格。", yaw_offset, YAW_OFFSET_MAX)


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
        ]

    def validate(self, image_bytes: bytes) -> tuple[bool, list[ValidationResult]]:
        context = build_context(image_bytes)
        results: list[ValidationResult] = []

        for validator in self.validators:
            result = validator.validate(context)
            results.append(result)
            if not result.passed and validator.name == "face_count":
                break

        return all(result.passed for result in results), results


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
    face_locations = face_recognition.face_locations(image_rgb, model="hog")
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
