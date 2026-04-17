import threading
import time

import cv2
import numpy as np

from scripts.config.config import cfg

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
                time.sleep(1)
                continue

            success, frame = self.capture.read()
            if not success or frame is None:
                self._set_frame(self._build_placeholder("camera read failed"))
                time.sleep(0.2)
                continue

            rendered = self._process_frame(frame)
            encoded = self._encode_frame(rendered)
            if encoded is not None:
                self._set_frame(encoded)
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
            return True

        self.capture.release()
        self.capture = None
        self.next_open_at = time.time() + 3
        return False

    def _process_frame(self, frame):
        frame = cv2.resize(frame, (cfg.camera_width, cfg.camera_height))

        if cfg.camera_mirror:
            frame = cv2.flip(frame, 1)

        if cfg.camera_rotate in {90, 180, 270}:
            rotate_map = {
                90: cv2.ROTATE_90_CLOCKWISE,
                180: cv2.ROTATE_180,
                270: cv2.ROTATE_90_COUNTERCLOCKWISE,
            }
            frame = cv2.rotate(frame, rotate_map[cfg.camera_rotate])

        self._update_face_locations(frame)
        self._draw_face_boxes(frame)
        self._draw_hud(frame)
        return frame

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

        cv2.rectangle(frame, (16, 16), (188, 92), (9, 17, 31), -1)
        cv2.rectangle(frame, (16, 16), (188, 92), (84, 243, 255), 1)
        cv2.putText(frame, "face3 terminal", (28, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (238, 244, 255), 1)
        cv2.putText(frame, status_text, (28, 64), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (93, 226, 165), 2)
        cv2.putText(frame, tips_text, (28, 84), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 207, 102), 1)

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
