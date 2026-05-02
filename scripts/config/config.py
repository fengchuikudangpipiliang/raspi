import json
import os
import time
from copy import deepcopy


DEFAULT_CONFIG = {
    "app_name": "face3",
    "debug_mode": True,
    "timezone": "Asia/Shanghai",
    "web_host": "0.0.0.0",
    "web_port": 5000,
    "reload": False,
    "camera_index": 0,
    "camera_width": 640,
    "camera_height": 480,
    "camera_fps": 20,
    "camera_jpeg_quality": 72,
    "camera_overlay_font_path": "",
    "camera_rotate": 0,
    "camera_mirror": False,
    "frame_resize_scale": 0.25,
    "detect_every_n_frames": 3,
    "recognition_target_fps": 5,
    "recognition_model": "face_recognition",
    "face_detection_model": "hog",
    "face_distance_threshold": 0.52,
    "face_match_required_times": 1,
    "unknown_face_label": "unknown",
    "sqlite_path": "data/face3.db",
    "sqlite_url": "sqlite:///data/face3.db",
    "sqlite_timeout": 30,
    "sqlite_echo": False,
    "sqlite_check_same_thread": False,
    "sqlite_auto_vacuum": "NONE",
    "sqlite_journal_mode": "WAL",
    "sqlite_synchronous": "NORMAL",
    "sqlite_foreign_keys": True,
    "faces_dir": "data/faces",
    "member_roster_path": "data/member_roster.csv",
    "session_secret_key": "face3-dev-change-this-secret",
    "session_cookie_name": "face3_session",
    "portal_max_face_profiles": 1,
    "portal_face_reupload_cooldown_seconds": 300,
    "portal_face_rejection_history_limit": 3,
    "snapshots_dir": "data/snapshots",
    "logs_dir": "logs",
    "attendance_cooldown_seconds": 60,
    "attendance_liveness_enabled": False,
    "attendance_liveness_model_path": "third_party/openvino_models_ir/public/anti-spoof-mn3/FP32/anti-spoof-mn3.xml",
    "attendance_liveness_device": "CPU",
    "attendance_liveness_real_threshold": 0.55,
    "attendance_liveness_gray_threshold": 0.30,
    "attendance_liveness_fail_required_times": 3,
    "attendance_rule_mode": "daily_once",
    "attendance_duplicate_block_seconds": 60,
    "attendance_daily_check_in_limit": 1,
    "attendance_policy_feedback_seconds": 4,
    "attendance_start_time": "00:00",
    "attendance_end_time": "23:59",
    "log_level": "INFO",
    "device_id": "face3-pi-01",
    "device_name": "Face3 Raspberry Pi",
    "device_location": "未设置",
    "admin_api_token": "face3-admin-change-this-token",
}


class AppConfig:
    _RESERVED_NAMES = {"reload", "get", "as_dict"}

    def __init__(self, config_path="env.json"):
        self._config_path = config_path
        self._last_mtime = 0.0
        self._data = {}
        self.reload()

    def _build_config(self, data):
        #其实就是先读取前面定义的默人配置，再读取传进来的env的data
        #如果有重复的key就覆盖掉默认配置的值，最后返回这个新的config
        config = deepcopy(DEFAULT_CONFIG)
        config.update(data)
        return config

    def reload(self):
        try:
            #得到文件的修改时间，如果没有修改就直接返回False
            mtime = os.path.getmtime(self._config_path)
            if mtime == self._last_mtime:
                return False

            with open(self._config_path, "r", encoding="utf-8") as file:
                loaded = json.load(file)
            #健壮性，看看加载的文件是不是一个dict，如果不是就抛出异常
            if not isinstance(loaded, dict):
                raise ValueError("config root must be object")

            new_data = self._build_config(loaded)
            #把旧配置里已经不存在的属性删掉
            for key, value in self._data.items():
                #not in就是在新的数据没有，但是在旧的实例属性里有，就删除这个属性
                if key in self._RESERVED_NAMES:
                    continue
                if key not in new_data and hasattr(self, key):
                    delattr(self, key)
            #把新配置逐项写到实例属性上
            for key, value in new_data.items():
                if key in self._RESERVED_NAMES:
                    continue
                setattr(self, key, value)

            self._data = new_data
            self._last_mtime = mtime
            print(f"[{time.strftime('%H:%M:%S')}] 配置类已经 reloaded")
            return True

        #如果 env.json 不存在，就直接使用 DEFAULT_CONFIG
        except FileNotFoundError:
            new_data = deepcopy(DEFAULT_CONFIG)
            for key, value in new_data.items():
                if key in self._RESERVED_NAMES:
                    continue
                setattr(self, key, value)
            self._data = new_data
            self._last_mtime = 0.0
            return False
        #任何其他错误，比如 JSON 格式写坏了
        except Exception as error:
            print(f"config reload failed: {error}")
            return False

    #先 reload(),再从 _data 里按字典方式取值,适合写成 cfg.get("web_port")
    def get(self, key, default=None):
        self.reload()
        return self._data.get(key, default)
    #返回 _data 的深拷贝,这样外部拿到的是副本，不会误改内部配置
    def as_dict(self):
        self.reload()
        return deepcopy(self._data)
    #它重写了 Python 的属性访问行为,访问的不是私有属性（不以 _ 开头）,并且不是 reload/get/as_dict 这几个方法
    #对于重写了这个方法的，都要这样写，用父类的，不然会无线调用
    def __getattribute__(self, name):
        if not name.startswith("_") and name not in self._RESERVED_NAMES:
            type(self).reload(self)
        return object.__getattribute__(self, name)

#表示模块加载时直接创建一个全局配置对象。
#别的文件只要 from scripts.config.config import cfg，就能直接用。
cfg = AppConfig()
