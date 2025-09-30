# learning_worker.py
import threading
import time
import os
import shutil
import cv2
import queue
from deepface import DeepFace

import config
from build_database import add_to_index # <-- IMPORT HÀM MỚI
from models import SessionLocal, Student, RecycleSession, FaceAudit

class LearningWorker(threading.Thread):
    def __init__(self, task_queue, face_recognizer_instance):
        super().__init__(daemon=True)
        self.task_queue = task_queue
        self.face_recognizer = face_recognizer_instance
        self.is_running = True

    def stop(self):
        self.is_running = False

    def run(self):
        print("[WORKER] Learning Worker da khoi dong.")
        while self.is_running:
            try:
                # Lấy nhiệm vụ từ hàng đợi, với timeout 1 giây để vòng lặp không bị block mãi mãi
                # Điều này giúp worker có thể dừng lại khi self.is_running = False
                task = self.task_queue.get(timeout=1)
                print(f"[WORKER] Nhan nhiem vu moi: {task}")

                self.process_task(task)

                # Đánh dấu nhiệm vụ đã hoàn thành
                self.task_queue.task_done()
            except queue.Empty: # Bắt lỗi khi hàng đợi rỗng sau 1 giây timeout
                continue # Tiếp tục vòng lặp để kiểm tra self.is_running
            except Exception as e:
                print(f"!!! LOI trong Learning Worker: {e}")

    def process_task(self, task):
        """
        Xử lý một nhiệm vụ học khuôn mặt mới.
        task = {
            "name": "Nguyen Van A",
            "class_name": "10A1",
            "unidentified_folder_path": "/path/to/unidentified/folder",
            "recycle_session_id": 123
        }
        """
        db = SessionLocal()
        try:
            # 1. Tìm kiếm học sinh trong CSDL
            student = db.query(Student).filter(
                Student.name == task['name'],
                Student.class_name == task['class_name']
            ).first()

            if not student:
                print(f"[WORKER] Khong tim thay hoc sinh {task['name']} - {task['class_name']}. Chuyen vao muc 'unresolved'.")
                unresolved_path = os.path.join(config.UNIDENTIFIED_PATH, 'unresolved')
                os.makedirs(unresolved_path, exist_ok=True)
                
                source_folder = task['unidentified_folder_path']
                # Lấy tên thư mục cuối cùng (ví dụ: 'Nguyen_Van_A_10A1_20231027_103000')
                folder_name = os.path.basename(source_folder)
                destination_folder = os.path.join(unresolved_path, folder_name)
                
                # Di chuyển thư mục
                shutil.move(source_folder, destination_folder)
                print(f"[WORKER] Da di chuyen {source_folder} -> {destination_folder}")
                return

            student_id = student.id
            print(f"[WORKER] Tim thay hoc sinh: ID {student_id}")

            # --- BẮT ĐẦU LOGIC MỚI: CẬP NHẬT PHIÊN TÁI CHẾ VÀ CỘNG ĐIỂM ---
            recycle_session_id = task.get('recycle_session_id')
            if recycle_session_id:
                # 1. Truy vấn bản ghi RecycleSession tương ứng
                session = db.query(RecycleSession).filter(RecycleSession.id == recycle_session_id).first()
                if session:
                    print(f"[WORKER] Tim thay phien tai che ID: {recycle_session_id} de cap nhat.")
                    # 2. Cập nhật student_id cho phiên đó
                    session.student_id = student_id

                    # 3. Lấy điểm thưởng đã được tính trước đó
                    points_to_add = session.points_awarded or 0

                    # 4. Cộng điểm vào tổng điểm của học sinh
                    if points_to_add > 0:
                        student.total_points = (student.total_points or 0) + points_to_add
                        print(f"[WORKER] Da cong {points_to_add} diem vao tong diem cua hoc sinh {student.name}.")
            # --- KẾT THÚC LOGIC MỚI ---

            # 2. Lặp qua các ảnh trong thư mục tạm và thực hiện QC
            image_files = [f for f in os.listdir(task['unidentified_folder_path']) if f.lower().endswith(('.jpg', '.png'))]
            
            added_count = 0
            new_embeddings_to_add = []
            new_ids_to_add = []

            for image_file in image_files:
                source_path = os.path.join(task['unidentified_folder_path'], image_file)
                
                # 3. Kiểm tra chất lượng (QC)
                qc_passed, status_message, face_img = self.quality_check(source_path)

                # 4. Ghi log audit
                audit_log = FaceAudit(
                    recycle_session_id=task.get('recycle_session_id'),
                    assigned_student_id=student_id,
                    source_image_path=source_path,
                    qc_passed=qc_passed,
                    status_message=status_message
                )
                db.add(audit_log)

                if qc_passed:
                    # 5. Di chuyển và đổi tên file ảnh đạt chuẩn
                    student_dataset_path = os.path.join(config.DATASET_PATH, str(student_id))
                    os.makedirs(student_dataset_path, exist_ok=True)
                    
                    timestamp = int(time.time() * 1000)
                    new_filename = f"capture_{timestamp}.jpg"
                    destination_path = os.path.join(student_dataset_path, new_filename)
                    
                    # Lưu ảnh khuôn mặt đã được cắt và căn chỉnh
                    cv2.imwrite(destination_path, face_img)

                    # Trích xuất embedding từ ảnh đã QC và lưu lại để thêm vào CSDL AI sau
                    try:
                        embedding_obj = DeepFace.represent(img_path=face_img, model_name=config.MODEL_NAME, enforce_detection=False, detector_backend='skip')
                        new_embeddings_to_add.append(embedding_obj[0]['embedding'])
                        new_ids_to_add.append(str(student_id))
                    except Exception as e:
                        print(f"!!! LOI khi trích xuất embedding cho ảnh mới: {e}")

                    audit_log.destination_image_path = destination_path
                    print(f"[WORKER] QC PASSED: Da luu anh moi tai {destination_path}")
                    added_count += 1
                else:
                    print(f"[WORKER] QC FAILED: {source_path} - Ly do: {status_message}")

            db.commit()

            # 6. Dọn dẹp thư mục tạm
            try:
                shutil.rmtree(task['unidentified_folder_path'])
                print(f"[WORKER] Da xoa thu muc tam: {task['unidentified_folder_path']}")
            except Exception as e:
                print(f"!!! LOI khi xoa thu muc tam: {e}")

            # 7. Cập nhật lại index AI nếu có ảnh mới
            if new_embeddings_to_add:
                print(f"[WORKER] Co {added_count} anh moi. Yeu cau xay dung lai CSDL AI...")
                # Gọi hàm thêm vào index thay vì build lại từ đầu
                add_to_index(new_embeddings_to_add, new_ids_to_add)
                # Yêu cầu FaceRecognizer tải lại dữ liệu
                self.face_recognizer.reload_data()

        except Exception as e:
            print(f"!!! LOI nghiem trong khi xu ly task: {e}")
            db.rollback()
        finally:
            db.close()

    def quality_check(self, image_path):
        """
        Kiểm tra chất lượng một ảnh: chỉ có 1 khuôn mặt, không quá mờ.
        :return: (bool: passed, str: message, image: cropped_face)
        """
        try:
            img = cv2.imread(image_path)
            if img is None:
                return False, "Cannot read image", None

            # Sử dụng MTCNN để phát hiện khuôn mặt (chính xác hơn)
            # Truyền img trực tiếp thay vì image_path để tránh đọc lại file
            faces = DeepFace.extract_faces(
                img_path=img,
                detector_backend=config.DETECTOR_BACKEND,
                enforce_detection=False
            )

            if len(faces) != 1:
                return False, f"Detected {len(faces)} faces", None
            
            # TODO: Thêm kiểm tra độ mờ (blur) và độ sáng (brightness)
            
            # Lấy ảnh khuôn mặt đã được căn chỉnh trả về từ DeepFace
            face_info = faces[0]
            # DeepFace trả về ảnh với channel BGR, nhưng giá trị pixel bị đảo ngược, cần convert lại
            cropped_face = (face_info['face'] * 255).astype('uint8')[:, :, ::-1]

            return True, "OK", cropped_face
        except Exception as e:
            return False, str(e), None