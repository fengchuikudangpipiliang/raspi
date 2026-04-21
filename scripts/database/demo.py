from scripts.database.sqlite_db import AttendanceRepository, init_db


def main():
    init_db()
    repo = AttendanceRepository()
    if not repo.list_users():
        user_id = repo.create_user("admin", "A001")
        repo.save_face_profile(user_id, "data/faces/admin.jpg", "[0.1, 0.2, 0.3]")
        repo.create_attendance_record(user_id, confidence=0.98)
    print(repo.list_users())
    print(repo.list_attendance_records())


if __name__ == "__main__":
    main()
阅读readme文档
本系统是基于树莓派的人脸识别考勤系统，你阅读整个项目，了解进展。
然后就是下一步，