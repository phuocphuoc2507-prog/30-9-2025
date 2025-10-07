# face_recognizer.py
import cv2
import faiss
import pickle
import numpy as np
from deepface import DeepFace
import config
import os
from models import SessionLocal, Student # <-- THAY ĐỔI: IMPORT TỪ MODELS

class FaceRecognizer:
    def __init__(self):
        """
        Hàm khởi tạo, tải tất cả các model và dữ liệu cần thiết lên.
        """
        self.reload_data()

    def reload_data(self):
        """
        Tải hoặc tải lại toàn bộ index và metadata.
        Hàm này sẽ được gọi bởi worker sau khi cập nhật dataset.
        """
        print("[AI] Dang tai/tai lai mo hinh AI va co so du lieu...")
        self.index = None
        self.student_ids = []
        self.student_info_map = {} # <-- THAY ĐỔI: Dùng dictionary thay cho DataFrame
        
        try:
            face_index_path = os.path.join(config.DATABASE_PATH, "face_index.faiss")
            student_ids_path = os.path.join(config.DATABASE_PATH, "student_ids.pkl")
            
            # Kiểm tra sự tồn tại của các file
            if not os.path.exists(face_index_path):
                raise FileNotFoundError(f"Không tìm thấy file index AI: {face_index_path}")
            if not os.path.exists(student_ids_path):
                raise FileNotFoundError(f"Không tìm thấy file student IDs: {student_ids_path}")
                
            self.index = faiss.read_index(face_index_path)
            with open(student_ids_path, "rb") as f:
                self.student_ids = pickle.load(f)

            # --- THAY ĐỔI LỚN: ĐỌC DỮ LIỆU TỪ SQLITE THAY VÌ CSV ---
            db = SessionLocal()
            try:
                all_students = db.query(Student).filter(Student.is_active == True).all()
                self.student_info_map = {
                    student.id: {"ho_ten": student.name, "lop": student.class_name}
                    for student in all_students
                }
            finally:
                db.close()
            # --- KẾT THÚC THAY ĐỔI ---
            print("[AI] Tai du lieu AI thanh cong.")
        except Exception as e:
            print(f"!!! LOI: Khong the tai CSDL AI. Hay chay file build_database.py. Chi tiet: {e}")

    def recognize(self, frame):
        """
        Hàm nhận diện chính, chứa logic cốt lõi từ file main_app.py cũ của bạn.
        :param frame: Một khung hình (ảnh) từ camera.
        :return: Một dictionary chứa kết quả và khoảng cách.
        """
        if self.index is None:
            return None

        try:
            # Để DeepFace tự xử lý việc phát hiện khuôn mặt bằng backend đã cấu hình
            # enforce_detection=True để đảm bảo chỉ xử lý khi có khuôn mặt
            embedding_objs = DeepFace.represent(img_path=frame,
                                               model_name=config.MODEL_NAME,
                                               detector_backend=config.DETECTOR_BACKEND,
                                               enforce_detection=True)

            # DeepFace.represent trả về list các object, mỗi object cho 1 khuôn mặt
            # Ta chỉ xử lý khuôn mặt đầu tiên (thường là rõ nhất/lớn nhất)
            embedding = np.array([embedding_objs[0]['embedding']], dtype='f4')
            faiss.normalize_L2(embedding)
            
            distances, indices = self.index.search(embedding, k=1)
            best_match_distance = distances[0][0]
            
            result_package = {"distance": best_match_distance, "info": None}

            if best_match_distance < config.RECOGNITION_THRESHOLD:
                best_match_index = indices[0][0]
                student_id = int(self.student_ids[best_match_index])
                # --- THAY ĐỔI: Tra cứu trong map thay vì DataFrame ---
                student_info = self.student_info_map.get(student_id)
                if student_info:
                    result_package["info"] = {"student_id": student_id, **student_info}
                else:
                    print(f"!!! CANH BAO: Nhan dien ra student_id {student_id} nhung khong tim thay trong CSDL.")
            return result_package
        except ValueError:
            # DeepFace sẽ ném ValueError nếu không tìm thấy khuôn mặt khi enforce_detection=True
            return None
        except Exception as e:
            # print(f"Loi khi nhan dien: {e}")
            return None