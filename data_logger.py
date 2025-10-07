# data_logger.py
from datetime import datetime
from models import SessionLocal, RecycleSession, Student

def log_recycling_event(student_id, ho_ten, lop, khoi_luong_kg, points_earned=0, unidentified_folder=None, commit_now=True):
    """
    Ghi lại một sự kiện tái chế vào bảng recycle_sessions trong CSDL.
    :param student_id: ID của học sinh (hoặc "UNKNOWN").
    :param ho_ten: Tên học sinh.
    :param lop: Lớp của học sinh.
    :param khoi_luong_kg: Khối lượng giấy đã tái chế.
    :param points_earned: Số điểm nhận được cho phiên này.
    :param unidentified_folder: Tên thư mục chứa ảnh người lạ (nếu có).
    :param commit_now: Nếu False, không commit và trả về session_id.
    :return: ID của session nếu commit_now=False, ngược lại trả về None.
    """
    db = SessionLocal()
    try:
        # Logic tìm/tạo student đã được chuyển sang main.py. Ở đây chỉ cần nhận student_id.

        new_session = RecycleSession(
            student_id=int(student_id) if student_id and student_id != "UNKNOWN" else None,
            timestamp=datetime.utcnow(),
            weight_kg=khoi_luong_kg,
            points_awarded=points_earned,
            unidentified_folder=unidentified_folder
        )
        db.add(new_session)

        # Flush để lấy ID của session mới tạo ra trước khi commit
        db.flush()
        session_id_to_return = new_session.id

        if commit_now:
            db.commit()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [LOG]: Da ghi nhan su kien tai che: {khoi_luong_kg:.3f} kg")
        return session_id_to_return
    except Exception as e:
        print(f"!!! LOI khi ghi file log: {e}")
        db.rollback()
    finally:
        db.close()