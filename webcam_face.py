import face_recognition
import cv2
import numpy as np
import time

# 获取摄像头句柄
video_capture = cv2.VideoCapture(0)

print("正在启动摄像头，按 'q' 退出...")

while True:
    start_time = time.time()
    
    # 1. 读取一帧
    ret, frame = video_capture.read()
    if not ret:
        break

    # 2. 缩小图片 (缩放为 1/4)，极大提升速度
    small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)

    # 3. 转换 BGR (OpenCV格式) 到 RGB (face_recognition格式)
    rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

    # 4. 检测人脸位置
    face_locations = face_recognition.face_locations(rgb_small_frame)

    # 5. 将坐标还原回原始大小并画框
    for (top, right, bottom, left) in face_locations:
        # 坐标乘以 4
        top *= 4
        right *= 4
        bottom *= 4
        left *= 4
        # 画矩形框
        cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)

    # 计算 FPS 并显示
    end_time = time.time()
    fps = 1 / (end_time - start_time)
    cv2.putText(frame, f"FPS: {fps:.2f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    # 6. 显示结果
    cv2.imshow('Face Recognition Testing', frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

video_capture.release()
cv2.destroyAllWindows()