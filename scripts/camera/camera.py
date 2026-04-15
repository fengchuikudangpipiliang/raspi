import cv2

class VideoCamera:
    def __init__(self, camera_index):
        # 接收外部传入的索引号
        self.video = cv2.VideoCapture(camera_index)
        
    def __del__(self):
        if self.video.isOpened():
            self.video.release()

    def get_frame(self):
        success, image = self.video.read()
        if not success:
            return None
        
        # 性能优化
        image = cv2.resize(image, (640, 480))
        ret, jpeg = cv2.imencode('.jpg', image)
        return jpeg.tobytes()