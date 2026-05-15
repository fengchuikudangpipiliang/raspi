import threading
import time
from math import ceil
from datetime import date
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from scripts.camera.frame_text import draw_text_items
from scripts.camera.strict_face_recognition import RecognitionResult
from scripts.camera.strict_face_recognition import StrictFaceRecognizer
from scripts.config.config import cfg
from scripts.database.sqlite_db import AttendanceRepository


class VideoCamera:
    """
    树莓派摄像头服务。

    当前采用“两线程分工”：
    1. 采集线程只负责尽快读取摄像头、叠加最近一次识别结果并持续推流。
    2. 识别线程只处理最新的一帧，避免重型人脸识别拖垮整个 MJPEG 刷新率。

    这样做的核心目标是：即使严格识别比较慢，终端画面依然尽量保持流畅。
    """

    def __init__(self, camera_index=None):
        self.camera_index = cfg.camera_index if camera_index is None else camera_index
        self.capture = None
        self.camera_sleep_seconds = 1 / max(cfg.camera_fps, 1)
        self.recognition_sleep_seconds = 1 / max(float(cfg.recognition_target_fps), 0.1)
        self.jpeg_quality = max(40, min(int(cfg.camera_jpeg_quality), 95))
        self.frame = self._build_placeholder("camera starting...")
        self.frame_lock = threading.Lock()
        self.recognition_frame_lock = threading.Lock()
        self.worker = None
        self.recognition_worker = None
        self.running = False

        self.face_locations = []
        self.frame_count = 0
        self.next_open_at = 0.0
        self.last_frame_at = None
        self.last_opened_at = None
        self.last_error = None
        self.read_failure_count = 0

        self.repo = AttendanceRepository()
        self.snapshots_dir = Path(cfg.snapshots_dir)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.snapshot_retention_days = max(int(cfg.attendance_snapshot_retention_days), 1)
        self.next_snapshot_cleanup_at = 0.0

        self.recognizer = None
        self.recognition_result: Optional[RecognitionResult] = None
        self.recognition_reload_interval_seconds = 60.0
        self.next_recognition_reload_at = 0.0
        self.last_attendance_record = None
        self.last_attendance_message = "等待识别"
        self.success_overlay_until = 0.0
        self.success_overlay_text = ""
        self.policy_feedback_until = 0.0
        self.last_policy_event = None

        self.latest_recognition_frame: Optional[np.ndarray] = None
        self.latest_recognition_frame_id = 0
        self.last_processed_recognition_frame_id = 0

        self._initialize_recognizer()

    def _initialize_recognizer(self) -> None:
        """
        初始化严格识别器并加载当前已生效的人脸档案。
        应用启动早期数据库可能还没完成迁移，因此这里既在构造期尝试一次，
        也会在 `start()` 前再次兜底，确保老库升级后不需要人工重启第二次。
        """

        try:
            self.recognizer = StrictFaceRecognizer()
            count = self.recognizer.reload_known_faces()
            self.next_recognition_reload_at = time.time() + self.recognition_reload_interval_seconds
            self.last_attendance_message = f"已加载 {count} 份人脸档案"
            self.last_error = None
        except Exception as error:
            self.recognizer = None
            self.last_error = f"recognizer_init_failed: {error}"

    def start(self):
        """
        启动摄像头采集线程和严格识别线程。
        """

        if self.running:
            return
        if self.recognizer is None:
            self._initialize_recognizer()
        self.running = True
        self.worker = threading.Thread(target=self._capture_loop, daemon=True)
        self.worker.start()

        if self.recognizer is not None:
            self.recognition_worker = threading.Thread(target=self._recognition_loop, daemon=True)
            self.recognition_worker.start()

    def stop(self):
        """
        停止所有后台线程并释放摄像头句柄。
        """

        self.running = False
        if self.worker and self.worker.is_alive():
            self.worker.join(timeout=1)
        if self.recognition_worker and self.recognition_worker.is_alive():
            self.recognition_worker.join(timeout=1)
        self.worker = None
        self.recognition_worker = None

        if self.capture is not None:
            self.capture.release()
            self.capture = None

    def get_frame(self):
        with self.frame_lock:
            return self.frame

    def frames(self):
        """
        对外提供 MJPEG 视频流。
        """

        while True:
            frame = self.get_frame()
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            )
            time.sleep(self.camera_sleep_seconds)

    def _capture_loop(self):
        """
        高频采集线程。
        它优先保障“画面更新”，不等待严格识别完成。
        """

        while self.running:
            loop_started_at = time.time()
            if not self._ensure_capture():
                self._set_frame(self._build_placeholder("camera unavailable"))
                self.last_error = "camera_unavailable"
                time.sleep(1)
                continue

            success, raw_frame = self.capture.read()
            if not success or raw_frame is None:
                self._set_frame(self._build_placeholder("camera read failed"))
                self.last_error = "camera_read_failed"
                self.read_failure_count += 1
                if self.read_failure_count >= 3:
                    self._reset_capture("camera_read_failed_reset")
                time.sleep(0.2)
                continue
            self.read_failure_count = 0

            normalized_frame = self._prepare_frame(raw_frame)
            self._publish_latest_recognition_frame(normalized_frame)
            rendered = self._render_frame(normalized_frame)
            encoded = self._encode_frame(rendered)
            if encoded is not None:
                self._set_frame(encoded)
                self.last_frame_at = time.time()

            elapsed = time.time() - loop_started_at
            remaining = self.camera_sleep_seconds - elapsed
            if remaining > 0:
                time.sleep(remaining)

    def _recognition_loop(self):
        """
        低频严格识别线程。
        只消费“最新的一帧”，不追赶历史帧，这样不会把视频流拖慢。
        """

        while self.running and self.recognizer is not None:
            loop_started_at = time.time()
            self._maybe_reload_recognizer()

            frame = self._consume_latest_recognition_frame()
            if frame is None:
                time.sleep(min(self.recognition_sleep_seconds, 0.05))
                continue

            try:
                result = self.recognizer.process_frame(
                    frame,
                    now=time.time(),
                    frame_already_normalized=True,
                )
                self.recognition_result = result
                self.face_locations = [result.location] if result.location else []
                self._update_recognition_status(result)

                if result.attendance_ready:
                    self._record_attendance(frame, result)

                self.last_error = None
            except Exception as error:
                self.recognition_result = None
                self.face_locations = []
                self.last_error = f"recognition_failed: {error}"

            elapsed = time.time() - loop_started_at
            remaining = self.recognition_sleep_seconds - elapsed
            if remaining > 0:
                time.sleep(remaining)

    def _ensure_capture(self):
        """
        确保 OpenCV 摄像头句柄可用。
        """

        if self.capture is not None and self.capture.isOpened():
            return True

        if time.time() < self.next_open_at:
            return False

        self.capture = cv2.VideoCapture(self.camera_index)
        camera_fourcc = str(getattr(cfg, "camera_fourcc", "") or "").strip().upper()
        if camera_fourcc:
            # 优先要求 USB 摄像头输出 MJPG 等压缩格式，避免部分设备在高分辨率下退回低清 YUYV 画面。
            self.capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*camera_fourcc[:4]))
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.camera_width)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.camera_height)
        self.capture.set(cv2.CAP_PROP_FPS, cfg.camera_fps)
        if self.capture.isOpened():
            self.last_opened_at = time.time()
            self.last_error = None
            self.read_failure_count = 0
            return True

        self.capture.release()
        self.capture = None
        self.next_open_at = time.time() + 3
        self.last_error = "camera_open_failed"
        return False

    def _prepare_frame(self, frame):
        """
        统一做尺寸、镜像和旋转处理。
        """

        resized = self._resize_for_display(frame)
        if self.recognizer is not None:
            return self.recognizer.prepare_frame(resized)

        return self._normalize_frame_fallback(resized)

    def _resize_for_display(self, frame):
        """
        按配置限制输出尺寸，但不把低分辨率摄像头画面强行放大。
        这样既能利用支持 720p 的摄像头，也避免不支持高分辨率的设备被软件插值放糊。
        """

        target_width = max(int(cfg.camera_width), 1)
        target_height = max(int(cfg.camera_height), 1)
        height, width = frame.shape[:2]
        if width <= target_width and height <= target_height:
            return frame

        scale = min(target_width / max(width, 1), target_height / max(height, 1))
        new_width = max(int(width * scale), 1)
        new_height = max(int(height * scale), 1)
        return cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)

    def _render_frame(self, normalized_frame):
        """
        用最近一次识别结果渲染视频帧。
        当前终端页默认保持纯视频画面，只在签到成功时叠加短暂提示。
        """

        rendered = normalized_frame.copy()
        if self.recognizer is None:
            self._draw_success_overlay(rendered)
            return rendered

        self.recognizer.annotate_frame(normalized_frame, self.recognition_result)
        self._draw_success_overlay(rendered)
        return rendered

    def _publish_latest_recognition_frame(self, frame):
        """
        发布最新帧给识别线程。
        旧帧会被直接覆盖，避免识别线程在落后时不断积压。
        """

        with self.recognition_frame_lock:
            self.latest_recognition_frame = frame.copy()
            self.latest_recognition_frame_id += 1

    def _consume_latest_recognition_frame(self) -> Optional[np.ndarray]:
        """
        识别线程只取最新的一帧。
        如果没有新帧，就返回 None。
        """

        with self.recognition_frame_lock:
            if self.latest_recognition_frame is None:
                return None
            if self.latest_recognition_frame_id == self.last_processed_recognition_frame_id:
                return None

            frame = self.latest_recognition_frame.copy()
            self.last_processed_recognition_frame_id = self.latest_recognition_frame_id
            return frame

    def _maybe_reload_recognizer(self):
        """
        定时热重载人脸库，避免新增人脸后必须重启服务。
        """

        if self.recognizer is None:
            return

        now = time.time()
        if now < self.next_recognition_reload_at:
            return

        try:
            count = self.recognizer.reload_known_faces()
            self.last_attendance_message = f"已加载 {count} 份人脸档案"
            self.last_error = None
        except Exception as error:
            self.last_error = f"recognizer_reload_failed: {error}"
        finally:
            self.next_recognition_reload_at = now + self.recognition_reload_interval_seconds

    def _update_recognition_status(self, result: Optional[RecognitionResult]):
        """
        把识别结果转成终端页 HUD 文案。
        """

        if result is None:
            self.last_attendance_message = "等待识别"
            return

        if result.attendance_ready and result.name and result.code:
            self.last_attendance_message = f"签到成功候选: {result.name}/{result.code}"
            return

        if result.recognized and result.name and result.code:
            self.last_attendance_message = (
                f"{result.name}/{result.code} 稳定帧 {result.stable_count}/{result.required_count}"
            )
            return

        if self.recognizer is not None:
            self.last_attendance_message = self.recognizer.describe_reason(result.reason)
            return

        self.last_attendance_message = result.reason

    def _record_attendance(self, frame, result: RecognitionResult):
        """
        严格识别真正通过后，把考勤记录和快照写入本地。
        """

        if self.recognizer is None or result.user_id is None:
            return

        decision = self._evaluate_attendance_policy(result)
        if not decision["allowed"]:
            self.last_attendance_message = decision["message"]
            self._set_policy_feedback(
                code=decision["code"],
                label=decision["label"],
                detail=decision["message"],
                percent=decision["percent"],
                allowed=False,
                result=result,
            )
            return

        try:
            snapshot_path = self._save_snapshot(frame, result)
            attendance_id = self.repo.create_attendance_record(
                user_id=result.user_id,
                check_type="check_in",
                snapshot_path=snapshot_path,
                confidence=result.confidence,
            )
            self.recognizer.mark_attendance_committed(result.user_id, result.timestamp)
            self.last_attendance_record = {
                "attendance_id": attendance_id,
                "user_id": result.user_id,
                "name": result.name,
                "code": result.code,
                "confidence": result.confidence,
                "snapshot_path": snapshot_path,
            }
            self.last_attendance_message = f"签到成功: {result.name}/{result.code}"
            self.success_overlay_text = f"{result.name} {result.code} 签到成功"
            self.success_overlay_until = time.time() + 4.0
            self._cleanup_expired_snapshots()
            self._set_policy_feedback(
                code="attendance_recorded",
                label="已签到",
                detail=self.success_overlay_text,
                percent=100,
                allowed=True,
                result=result,
                extra={
                    "attendance_id": attendance_id,
                    "snapshot_path": snapshot_path,
                },
            )
            self.last_error = None
        except Exception as error:
            self.last_error = f"attendance_write_failed: {error}"
            self.last_attendance_message = "签到写入失败"

    def _save_snapshot(self, frame, result: RecognitionResult) -> str:
        """
        保存签到时的现场快照。
        """

        date_dir = self.snapshots_dir / datetime.now().strftime("%Y%m%d")
        date_dir.mkdir(parents=True, exist_ok=True)
        safe_code = (result.code or "unknown").replace("/", "_")
        file_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{safe_code}.jpg"
        file_path = date_dir / file_name
        if not cv2.imwrite(str(file_path), frame):
            raise RuntimeError("snapshot_save_failed")

        try:
            return str(file_path.relative_to(Path.cwd()))
        except ValueError:
            return str(file_path)

    def _cleanup_expired_snapshots(self):
        """
        清理超过保留期的签到现场快照。
        这里只删除本地图片目录，不删除数据库考勤流水，避免影响历史统计。
        """

        now = time.time()
        if now < self.next_snapshot_cleanup_at:
            return

        self.next_snapshot_cleanup_at = now + 24 * 60 * 60
        cutoff_date = date.today() - timedelta(days=self.snapshot_retention_days - 1)
        try:
            for child in self.snapshots_dir.iterdir():
                if not child.is_dir():
                    continue
                try:
                    folder_date = datetime.strptime(child.name, "%Y%m%d").date()
                except ValueError:
                    continue
                if folder_date >= cutoff_date:
                    continue
                for file_path in child.iterdir():
                    if file_path.is_file():
                        file_path.unlink()
                try:
                    child.rmdir()
                except OSError:
                    pass
        except Exception as error:
            self.last_error = f"snapshot_cleanup_failed: {error}"

    def _draw_success_overlay(self, frame):
        """
        只在签到成功后的短时间内显示简洁提示，不再叠加常驻调试 UI。
        """

        if time.time() > self.success_overlay_until or not self.success_overlay_text:
            return
        if self.recognition_result is not None and self.recognition_result.reason == "no_face":
            return

        panel_height = 72
        panel_top = max(frame.shape[0] - panel_height - 18, 12)
        cv2.rectangle(frame, (18, panel_top), (frame.shape[1] - 18, frame.shape[0] - 18), (8, 24, 18), -1)
        cv2.rectangle(frame, (18, panel_top), (frame.shape[1] - 18, frame.shape[0] - 18), (93, 226, 165), 1)
        rendered = draw_text_items(
            frame,
            [
                {
                    "text": "签到成功",
                    "position": (34, panel_top + 14),
                    "font_size": 18,
                    "fill": (93, 226, 165),
                },
                {
                    "text": self.success_overlay_text[:30],
                    "position": (34, panel_top + 38),
                    "font_size": 20,
                    "fill": (238, 244, 255),
                },
            ],
        )
        frame[:, :] = rendered

    def _normalize_frame_fallback(self, frame):
        """
        严格识别器不可用时，仍按项目配置做镜像和旋转。
        """

        rendered = frame
        if cfg.camera_mirror:
            rendered = cv2.flip(rendered, 1)

        if cfg.camera_rotate in {90, 180, 270}:
            rotate_map = {
                90: cv2.ROTATE_90_CLOCKWISE,
                180: cv2.ROTATE_180,
                270: cv2.ROTATE_90_COUNTERCLOCKWISE,
            }
            rendered = cv2.rotate(rendered, rotate_map[cfg.camera_rotate])

        return rendered

    def _encode_frame(self, frame):
        """
        把视频帧压成 JPEG。
        质量参数做成配置项，便于在流畅度和清晰度之间平衡。
        """

        success, jpeg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality])
        if not success:
            return None
        return jpeg.tobytes()

    def _set_frame(self, frame):
        with self.frame_lock:
            self.frame = frame

    def _reset_capture(self, error_code: str):
        """
        连续读帧失败时主动释放摄像头，让下一轮按正常流程重连。
        """

        if self.capture is not None:
            self.capture.release()
        self.capture = None
        self.next_open_at = time.time() + 1.0
        self.last_error = error_code
        self.read_failure_count = 0

    def _build_placeholder(self, message):
        """
        摄像头异常时的占位画面。
        """

        frame = np.zeros((cfg.camera_height, cfg.camera_width, 3), dtype=np.uint8)
        frame[:] = (8, 16, 29)
        rendered = draw_text_items(
            frame,
            [
                {
                    "text": "摄像头终端",
                    "position": (40, 52),
                    "font_size": 28,
                    "fill": (84, 243, 255),
                },
                {
                    "text": self._build_placeholder_message(message),
                    "position": (40, 104),
                    "font_size": 22,
                    "fill": (238, 244, 255),
                },
                {
                    "text": "请检查摄像头编号配置或访问权限",
                    "position": (40, 152),
                    "font_size": 18,
                    "fill": (255, 207, 102),
                },
            ],
        )
        return self._encode_frame(rendered)

    def _build_placeholder_message(self, message: str) -> str:
        """
        把占位页的英文错误提示转成更适合现场排查的中文提示。
        """

        mapping = {
            "camera starting...": "摄像头正在启动",
            "camera unavailable": "当前无法打开摄像头",
            "camera read failed": "摄像头读取失败",
        }
        return mapping.get(message, message)

    def get_terminal_progress(self) -> dict:
        """
        返回终端页左上角小进度提示所需的轻量状态。
        """

        now = time.time()
        result = self.recognition_result

        if result is not None and result.reason == "no_face":
            return {
                "label": "等待人脸",
                "detail": "请进入画面中央",
                "percent": 10,
            }

        if now <= self.success_overlay_until and self.success_overlay_text:
            return {
                "label": "已签到",
                "detail": self.success_overlay_text,
                "percent": 100,
            }
        if now <= self.policy_feedback_until and self.last_policy_event:
            return {
                "label": self.last_policy_event["label"],
                "detail": self.last_policy_event["detail"],
                "percent": self.last_policy_event["percent"],
            }

        if self.capture is None or not self.capture.isOpened():
            return {
                "label": "摄像头离线",
                "detail": "等待摄像头恢复",
                "percent": 0,
            }

        if result is None:
            return {
                "label": "等待人脸",
                "detail": "请单人正对镜头",
                "percent": 10,
            }

        if result.reason == "no_face":
            return {
                "label": "等待人脸",
                "detail": "请进入画面中央",
                "percent": 10,
            }
        if result.reason == "multi_face":
            return {
                "label": "多人入镜",
                "detail": "请保持单人签到",
                "percent": 10,
            }
        if result.reason == "face_too_small":
            return {
                "label": "靠近一点",
                "detail": "脸部再靠近镜头一些",
                "percent": 25,
            }
        if result.reason == "spoof_suspected":
            return {
                "label": "疑似假脸",
                "detail": "请真人正对镜头签到",
                "percent": 15,
            }
        if result.reason == "liveness_uncertain":
            return {
                "label": "正在确认",
                "detail": "请保持在画面中央",
                "percent": 30,
            }
        if result.reason == "liveness_challenge_turn_left":
            return {
                "label": "向左转头",
                "detail": "轻微转头后再回正",
                "percent": 55,
            }
        if result.reason == "liveness_challenge_turn_right":
            return {
                "label": "向右转头",
                "detail": "轻微转头后再回正",
                "percent": 55,
            }
        if result.reason == "liveness_challenge_front":
            return {
                "label": "回到正脸",
                "detail": "请重新正对摄像头",
                "percent": 72,
            }
        if result.reason == "liveness_face_crop_failed":
            return {
                "label": "重新对准",
                "detail": "请把脸完整放入画面中央",
                "percent": 25,
            }
        if result.reason == "face_encoding_failed":
            return {
                "label": "重新对准",
                "detail": "请保持正脸稳定",
                "percent": 35,
            }
        if result.reason == "unknown":
            return {
                "label": "未匹配",
                "detail": "当前人脸不在库中",
                "percent": 45,
            }
        if result.reason == "ambiguous_match":
            return {
                "label": "结果接近",
                "detail": "请单人重试",
                "percent": 50,
            }
        if result.attendance_ready:
            return {
                "label": "准备签到",
                "detail": "正在写入考勤",
                "percent": 95,
            }
        if result.reason == "attendance_cooldown":
            return {
                "label": "已签到",
                "detail": "刚完成签到，请稍后再试",
                "percent": 100,
            }
        if result.reason == "outside_attendance_window":
            return {
                "label": "非考勤时段",
                "detail": "当前不在允许签到时间内",
                "percent": 90,
            }
        if result.recognized and result.name and result.code:
            return {
                "label": "已匹配",
                "detail": f"{result.name} / {result.code}",
                "percent": 88,
            }

        return {
            "label": "识别中",
            "detail": "正在进行人脸比对",
            "percent": 60,
        }

    def _evaluate_attendance_policy(self, result: RecognitionResult) -> dict:
        """
        在真正写考勤前做业务规则判断。
        当前支持测试用的“固定时间间隔内只允许写一次”，也支持后续切回“每天一次签到”。
        """

        if result.user_id is None:
            return {
                "allowed": False,
                "code": "attendance_missing_user",
                "label": "签到失败",
                "message": "当前识别结果缺少用户信息。",
                "percent": 0,
            }

        mode = str(cfg.attendance_rule_mode or "daily_once").strip().lower()
        duplicate_block_seconds = max(int(cfg.attendance_duplicate_block_seconds or 0), 0)
        daily_limit = max(int(cfg.attendance_daily_check_in_limit or 1), 1)
        check_type = "check_in"
        date_text = datetime.fromtimestamp(result.timestamp).astimezone().date().isoformat()

        latest_record = self.repo.get_latest_attendance_record_for_user(result.user_id, check_type=check_type)
        if latest_record and duplicate_block_seconds > 0:
            elapsed_seconds = self._seconds_since_attendance(latest_record["check_time"], result.timestamp)
            if elapsed_seconds is not None and elapsed_seconds < duplicate_block_seconds:
                remaining_seconds = max(duplicate_block_seconds - elapsed_seconds, 0.0)
                return {
                    "allowed": False,
                    "code": "attendance_duplicate_interval_blocked",
                    "label": "重复签到",
                    "message": f"当前规则限制 {duplicate_block_seconds} 秒内只允许签到一次，还需等待 {ceil(remaining_seconds)} 秒。",
                    "percent": 100,
                }

        if mode == "daily_once":
            today_count = self.repo.count_attendance_records_for_user_on_date(
                result.user_id,
                date_text,
                check_type=check_type,
            )
            if today_count >= daily_limit:
                return {
                    "allowed": False,
                    "code": "attendance_daily_limit_reached",
                    "label": "今日已签到",
                    "message": f"当前规则限制每天最多签到 {daily_limit} 次，今天已经完成签到。",
                    "percent": 100,
                }

        return {
            "allowed": True,
            "code": "attendance_allowed",
            "label": "准备签到",
            "message": "规则校验通过，允许写入考勤。",
            "percent": 95,
        }

    def _seconds_since_attendance(self, check_time_text: str, now_timestamp: float) -> Optional[float]:
        """
        计算最近一条考勤记录距离当前识别时刻经过了多少秒。
        """

        if not check_time_text:
            return None
        try:
            check_time = datetime.strptime(check_time_text, "%Y-%m-%d %H:%M:%S").astimezone()
        except ValueError:
            return None
        now_dt = datetime.fromtimestamp(now_timestamp).astimezone()
        return max((now_dt - check_time).total_seconds(), 0.0)

    def _set_policy_feedback(
        self,
        *,
        code: str,
        label: str,
        detail: str,
        percent: int,
        allowed: bool,
        result: Optional[RecognitionResult] = None,
        extra: Optional[dict] = None,
    ) -> None:
        """
        缓存最近一次业务规则判定结果，供终端页和管理员 API 读取。
        """

        self.policy_feedback_until = time.time() + max(float(cfg.attendance_policy_feedback_seconds or 0), 0.0)
        payload = {
            "code": code,
            "label": label,
            "detail": detail,
            "percent": int(percent),
            "allowed": bool(allowed),
            "at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        if result is not None:
            payload.update(
                {
                    "user_id": result.user_id,
                    "name": result.name,
                    "code_text": result.code,
                }
            )
        if extra:
            payload.update(extra)
        self.last_policy_event = payload
