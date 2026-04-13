import cv2

# 0 通常是 USB 摄像头的默认索引
cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("错误：无法打开摄像头。请检查连接或权限。")
else:
    print("摄像头已成功打开！按 'q' 键退出测试窗口。")

while True:
    ret, frame = cap.read()
    if not ret:
        print("错误：无法获取画面帧。")
        break

    # 显示画面
    cv2.imshow('Camera Test', frame)

    # 按 q 退出
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()