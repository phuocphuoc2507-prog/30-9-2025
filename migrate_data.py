# migrate_data.py
import pandas as pd
from models import SessionLocal, Student, init_db
import config

def migrate_students_from_csv():
    """
    Đọc dữ liệu từ metadata.csv và import vào bảng 'students' trong CSDL SQLite.
    Hàm này sẽ bỏ qua các học sinh đã tồn tại trong CSDL.
    """
    print("--- Bat dau qua trinh di cu du lieu hoc sinh ---")

    # 1. Khởi tạo CSDL và các bảng
    init_db()

    db = SessionLocal()

    try:
        # 2. Đọc file metadata.csv
        df_meta = pd.read_csv(config.METADATA_FILE)
        print(f"Tim thay {len(df_meta)} hoc sinh trong file {config.METADATA_FILE}.")

        imported_count = 0
        skipped_count = 0

        # 3. Lặp qua từng dòng trong file CSV
        for _, row in df_meta.iterrows():
            student_id = int(row['student_id'])

            # Kiểm tra xem student_id đã tồn tại trong CSDL chưa
            exists = db.query(Student).filter(Student.id == student_id).first()

            if not exists:
                # Nếu chưa tồn tại, tạo đối tượng Student mới và thêm vào session
                new_student = Student(
                    id=student_id,
                    name=row['ho_ten'],
                    class_name=row['lop'],
                    total_points=0 # Bắt đầu với 0 điểm
                )
                db.add(new_student)
                imported_count += 1
                print(f"  -> Dang import hoc sinh: ID={student_id}, Ten={row['ho_ten']}")
            else:
                # Nếu đã tồn tại, bỏ qua
                skipped_count += 1
                print(f"  -> Bo qua hoc sinh da ton tai: ID={student_id}")

        # 4. Commit tất cả thay đổi vào CSDL
        if imported_count > 0:
            db.commit()

        print("\n--- Hoan tat di cu du lieu ---")
        print(f"Da import: {imported_count} hoc sinh moi.")
        print(f"Da bo qua: {skipped_count} hoc sinh da ton tai.")

    except FileNotFoundError:
        print(f"!!! LOI: Khong tim thay file metadata.csv tai duong dan: {config.METADATA_FILE}")
    except Exception as e:
        print(f"!!! Da xay ra loi trong qua trinh di cu: {e}")
        db.rollback() # Hoàn tác nếu có lỗi
    finally:
        db.close() # Luôn đóng session

if __name__ == "__main__":
    migrate_students_from_csv()
