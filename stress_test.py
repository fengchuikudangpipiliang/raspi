import face_recognition
import cv2
import time

cap = cv2.VideoCapture(0)
ret, frame = cap.read()
cap.release()

if ret:
    # 将 BGR 转换为 RGB
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    
    print("开始人脸检测压力测试...")
    start_time = time.time()
    
    # 测试定位人脸
    face_locations = face_recognition.face_locations(rgb_frame)
    
    end_time = time.time()
    
    print(f"测试完成！")
    print(f"检测到人脸数量: {len(face_locations)}")
    print(f"单帧检测耗时: {end_time - start_time:.4f} 秒")
else:
    print("未能捕获图像")