import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from scripts.config.config import cfg
from scripts.database.sqlite_db import AttendanceRepository
from scripts.camera.strict_face_recognition import StrictFaceRecognizer
from scripts.camera.strict_face_recognition import RecognitionResult

try:
    import face_recognition
except Exception:
    face_recognition = None


class VideoCamera:
    def __init__(self, camera_index=None):
        self.camera_index = cfg.camera_index if camera_index is None else camera_index
        self.capture = None
        self.frame = self._build_placeholder("camera starting...")
        self.lock = threading.Lock()
        self.worker = None
        self.running = False
        self.face_locations = []
        self.frame_count = 0
        self.next_open_at = 0.0
        self.last_frame_at = None
        self.last_opened_at = None
        self.last_error = None
        self.repo = AttendanceRepository()
        self.snapshots_dir = Path(cfg.snapshots_dir)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.recognizer = None
        self.recognition_result: Optional[RecognitionResult] = None
        self.recognition_reload_interval_seconds = 60.0
        self.next_recognition_reload_at = 0.0
        self.last_attendance_record = None
        self.last_attendance_message = "等待识别"

        try:
            self.recognizer = StrictFaceRecognizer()
            self.recognizer.reload_known_faces()
            self.next_recognition_reload_at = time.time() + self.recognition_reload_interval_seconds
        except Exception as error:
            self.recognizer = None
            self.last_error = f"recognizer_init_failed: {error}"

    def start(self):
        if self.running:
            return
        self.running = True
        self.worker = threading.Thread(target=self._capture_loop, daemon=True)
        self.worker.start()

    def stop(self):
        self.running = False
        if self.worker and self.worker.is_alive():
            self.worker.join(timeout=1)
        self.worker = None
        if self.capture is not None:
            self.capture.release()
            self.capture = None

    def get_frame(self):
        with self.lock:
            return self.frame

    def frames(self):
        sleep_time = 1 / max(cfg.camera_fps, 1)
        while True:
            frame = self.get_frame()
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            )
            time.sleep(sleep_time)

    def _capture_loop(self):
        sleep_time = 1 / max(cfg.camera_fps, 1)
        while self.running:
            if not self._ensure_capture():
                self._set_frame(self._build_placeholder("camera unavailable"))
                self.last_error = "camera_unavailable"
                time.sleep(1)
                continue

            success, frame = self.capture.read()
            if not success or frame is None:
                self._set_frame(self._build_placeholder("camera read failed"))
                self.last_error = "camera_read_failed"
                time.sleep(0.2)
                continue

            rendered = self._process_frame(frame)
            encoded = self._encode_frame(rendered)
            if encoded is not None:
                self._set_frame(encoded)
                self.last_frame_at = time.time()
                self.last_error = None
            time.sleep(sleep_time)

    def _ensure_capture(self):
        if self.capture is not None and self.capture.isOpened():
            return True

        if time.time() < self.next_open_at:
            return False

        self.capture = cv2.VideoCapture(self.camera_index)
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.camera_width)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.camera_height)
        self.capture.set(cv2.CAP_PROP_FPS, cfg.camera_fps)
        if self.capture.isOpened():
            self.last_opened_at = time.time()
            self.last_error = None
            return True

        self.capture.release()
        self.capture = None
        self.next_open_at = time.time() + 3
        self.last_error = "camera_open_failed"
        return False

    def _process_frame(self, frame):
        frame = cv2.resize(frame, (cfg.camera_width, cfg.camera_height))
        if self.recognizer is None:
            self._update_face_locations(frame)
            self._draw_face_boxes(frame)
            self._draw_hud(frame)
            return frame

        frame = self.recognizer.prepare_frame(frame)
        self._maybe_reload_recognizer()
        self._update_recognition(frame)
        rendered = self.recognizer.annotate_frame(frame, self.recognition_result)
        self._draw_hud(rendered)
        return rendered

    def _maybe_reload_recognizer(self):
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

    def _update_recognition(self, frame):
        if self.recognizer is None:
            self.face_locations = []
            self.recognition_result = None
            return

        self.frame_count += 1
        detect_every = max(cfg.detect_every_n_frames, 1)
        if self.frame_count % detect_every == 0:
            try:
                self.recognition_result = self.recognizer.process_frame(
                    frame,
                    now=time.time(),
                    frame_already_normalized=True,
                )
                self.last_error = None
            except Exception as error:
                self.recognition_result = None
                self.face_locations = []
                self.last_error = f"recognition_failed: {error}"
                return

            if self.recognition_result and self.recognition_result.location:
                self.face_locations = [self.recognition_result.location]
            else:
                self.face_locations = []

            self._update_recognition_status()
            if self.recognition_result and self.recognition_result.attendance_ready:
                self._record_attendance(frame, self.recognition_result)
            return

        if self.recognition_result and self.recognition_result.location:
            self.face_locations = [self.recognition_result.location]
        else:
            self.face_locations = []

    def _update_recognition_status(self):
        result = self.recognition_result
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
        self.last_attendance_message = result.reason

    def _record_attendance(self, frame, result: RecognitionResult):
        if self.recognizer is None or result.user_id is None:
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
            self.last_error = None
        except Exception as error:
            self.last_error = f"attendance_write_failed: {error}"
            self.last_attendance_message = "签到写入失败"

    def _save_snapshot(self, frame, result: RecognitionResult) -> str:
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

    def _update_face_locations(self, frame):
        self.frame_count += 1
        detect_every = max(cfg.detect_every_n_frames, 1)

        if self.frame_count % detect_every != 0:
            return

        if face_recognition is None:
            self.face_locations = []
            return

        scale = min(max(cfg.frame_resize_scale, 0.1), 1.0)
        small_frame = cv2.resize(frame, (0, 0), fx=scale, fy=scale)
        rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

        try:
            raw_locations = face_recognition.face_locations(
                rgb_small_frame,
                model=cfg.face_detection_model,
            )
        except Exception:
            raw_locations = []

        scaled_locations = []
        for top, right, bottom, left in raw_locations:
            scaled_locations.append(
                (
                    int(top / scale),
                    int(right / scale),
                    int(bottom / scale),
                    int(left / scale),
                )
            )
        self.face_locations = scaled_locations

    def _draw_face_boxes(self, frame):
        for top, right, bottom, left in self.face_locations:
            cv2.rectangle(frame, (left, top), (right, bottom), (84, 243, 255), 2)
            cv2.rectangle(frame, (left, bottom - 32), (right, bottom), (84, 243, 255), cv2.FILLED)
            cv2.putText(
                frame,
                "face",
                (left + 10, bottom - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (9, 17, 31),
                2,
            )

    def _draw_hud(self, frame):
        face_count = len(self.face_locations)
        status_text = f"faces: {face_count}"
        tips_text = "streaming" if self.capture is not None and self.capture.isOpened() else "offline"

        cv2.rectangle(frame, (16, 16), (420, 116), (9, 17, 31), -1)
        cv2.rectangle(frame, (16, 16), (420, 116), (84, 243, 255), 1)
        cv2.putText(frame, "face3 terminal", (28, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (238, 244, 255), 1)
        cv2.putText(frame, status_text, (28, 64), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (93, 226, 165), 2)
        cv2.putText(frame, tips_text, (28, 84), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 207, 102), 1)
        cv2.putText(
            frame,
            self.last_attendance_message[:42],
            (28, 106),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (238, 244, 255),
            1,
        )

    def _encode_frame(self, frame):
        success, jpeg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if not success:
            return None
        return jpeg.tobytes()

    def _set_frame(self, frame):
        with self.lock:
            self.frame = frame

    def _build_placeholder(self, message):
        frame = np.zeros((cfg.camera_height, cfg.camera_width, 3), dtype=np.uint8)
        frame[:] = (8, 16, 29)
        cv2.putText(frame, "face3 camera", (40, 80), cv2.FONT_HERSHEY_SIMPLEX, 1, (84, 243, 255), 2)
        cv2.putText(frame, message, (40, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (238, 244, 255), 2)
        cv2.putText(frame, "check camera_index or camera permissions", (40, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 207, 102), 1)
        return self._encode_frame(frame)
