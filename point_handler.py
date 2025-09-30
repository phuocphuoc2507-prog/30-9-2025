# point_handler.py
import config
from models import SessionLocal, Student, RecycleSession
from datetime import datetime

def add_points(student_id, paper_weight_kg, ho_ten=None, lop=None, unidentified_folder=None):
    """
    Cộng điểm cho học sinh, đồng thời tạo bản ghi RecycleSession trong cùng một transaction.
    :param student_id: ID của học sinh
    :param paper_weight_kg: Khối lượng giấy tính bằng kg
    :return: (điểm nhận được, tổng điểm hiện tại)
    """
    # Kiểm tra nếu là người lạ thì không cộng điểm
    if not student_id or student_id == "UNKNOWN":
        print("[POINTS] Không cộng điểm cho người lạ")
        return 0, 0

    try:
        student_id = int(student_id)
    except (ValueError, TypeError):
        print(f"!!! LOI: student_id không hợp lệ: {student_id}")
        return 0, 0

    points_to_add = round(paper_weight_kg * 1000 * config.POINTS_PER_GRAM)

    if points_to_add <= 0:
        print("[POINTS]: Khong du khoi luong de them diem.")
        return 0, get_student_points(student_id)

    db = SessionLocal()
    try:
        # Tìm học sinh trong CSDL
        student = db.query(Student).filter(Student.id == student_id).first()

        if student:
            # Nếu tìm thấy, cộng điểm
            student.total_points += points_to_add

            # TẠO BẢN GHI RECYCLESESSION MỚI
            new_session = RecycleSession(
                student_id=student_id,
                timestamp=datetime.utcnow(),
                weight_kg=paper_weight_kg,
                points_awarded=points_to_add,
                unidentified_folder=unidentified_folder
            )
            db.add(new_session)
            db.commit()
            db.refresh(student) # Cập nhật lại thông tin student từ CSDL
            new_total_points = student.total_points
            print(f"[POINTS]: Cong {points_to_add} diem cho hoc sinh {student_id}. Tong diem moi: {new_total_points}")
            return int(points_to_add), int(new_total_points)
        else:
            # Nếu không tìm thấy, có thể là dữ liệu chưa đồng bộ.
            # Trong thực tế, bạn có thể tạo mới học sinh ở đây nếu cần.
            # Hiện tại, chỉ log lỗi và trả về 0.
            print(f"!!! CANH BAO: Khong tim thay hoc sinh voi ID {student_id} trong CSDL de cong diem.")
            return 0, 0

    except Exception as e:
        print(f"!!! LOI khi cong diem trong CSDL: {e}")
        db.rollback()
        return 0, get_student_points(student_id)
    finally:
        db.close()

def get_student_points(student_id):
    """ Lấy điểm hiện tại của học sinh """
    db = SessionLocal()
    try:
        student = db.query(Student).filter(Student.id == int(student_id)).first()
        if student:
            return student.total_points
        return 0
    except (ValueError, TypeError, Exception):
        return 0
    finally:
        db.close()

def add_points_and_update_session(session_id, paper_weight_kg):
    """
    Cập nhật khối lượng cho một session đã tồn tại (dành cho người lạ)
    và cộng điểm nếu student_id đã được worker cập nhật.
    :param session_id: ID của RecycleSession
    :param paper_weight_kg: Khối lượng giấy
    :return: (điểm nhận được, tổng điểm hiện tại)
    """
    points_to_add = round(paper_weight_kg * 1000 * config.POINTS_PER_GRAM)
    if points_to_add <= 0:
        return 0, 0

    db = SessionLocal()
    try:
        session = db.query(RecycleSession).filter(RecycleSession.id == session_id).first()
        if not session:
            print(f"!!! LOI: Khong tim thay session voi ID {session_id} de cap nhat.")
            return 0, 0

        # Cập nhật khối lượng và điểm cho session
        session.weight_kg = paper_weight_kg
        session.points_awarded = points_to_add

        # Nếu worker đã cập nhật student_id cho session này, cộng điểm cho học sinh
        if session.student_id:
            student = db.query(Student).filter(Student.id == session.student_id).first()
            if student:
                student.total_points += points_to_add
                db.commit()
                db.refresh(student)
                return int(points_to_add), int(student.total_points)
        
        db.commit()
        return 0, 0 # Trả về 0 điểm nếu chưa có student_id
    except Exception as e:
        print(f"!!! LOI khi cap nhat session va cong diem: {e}")
        db.rollback()
        return 0, 0
    finally:
        db.close()