# main.py
import time
import cv2
import os
from datetime import datetime
import numpy as np
import random
import base64
from flask import Flask, render_template
from flask_socketio import SocketIO
import threading
import keyboard
import queue # <-- THÊM THƯ VIỆN HÀNG ĐỢI
import re, unicodedata

# --- KÍCH HOẠT HỖ TRỢ MÃ ANSI TRÊN WINDOWS ---
if os.name == 'nt':
    os.system('')

# --- KHỞI TẠO CÁC MODULE ---
import config
import hardware_handler
from models import SessionLocal, Student # <-- IMPORT CÁC MODEL CẦN THIẾT
import data_logger
from face_recognizer import FaceRecognizer
import point_handler # <-- IMPORT MODULE MỚI
from learning_worker import LearningWorker # <-- THÊM WORKER

# Đảm bảo các thư mục cần thiết tồn tại
required_dirs = [
    config.UNIDENTIFIED_PATH,
    config.DATABASE_PATH,
    config.DATASET_PATH
]

for dir_path in required_dirs:
    try:
        if not os.path.exists(dir_path):
            print(f"[INIT] Tao thu muc: {dir_path}")
            os.makedirs(dir_path, exist_ok=True)
        if not os.access(dir_path, os.W_OK):
            print(f"!!! CANH BAO: Khong co quyen ghi vao thu muc {dir_path}")
    except Exception as e:
        print(f"!!! LOI khi tao thu muc {dir_path}: {str(e)}")

print("[INIT] Da kiem tra va tao cac thu muc can thiet")

# --- KHỞI TẠO FLASK & SOCKETIO ---
app = Flask(__name__)
socketio = SocketIO(app)

# --- CÁC BIẾN TOÀN CỤC ---
state = "IDLE"
load_cell_1 = hardware_handler.LoadCell(bin_number=1)
load_cell_2 = hardware_handler.LoadCell(bin_number=2)
recognizer = FaceRecognizer()
cap = None
recognition_start_time = 0

# --- HÀNG ĐỢI VÀ WORKER CHO VIỆC HỌC (MỚI) ---
learning_task_queue = queue.Queue()
learning_worker_thread = LearningWorker(learning_task_queue, recognizer)

current_transaction_info = {}
manual_trigger = False
idle_message_printed = False # <-- BIẾN CỜ: Dùng để kiểm tra đã in thông báo IDLE chưa

# --- HÀM LẮNG NGHE BÀN PHÍM ---
def key_listener():
    global manual_trigger
    while True:
        try:
            keyboard.wait('h')
            if state == "IDLE":
                print("\n[MANUAL TRIGGER] Da nhan phim 'h'. Kich hoat he thong!")
                manual_trigger = True
        except Exception:
            break

# --- CÁC HÀM TIỆN ÍCH ---
def safe_folder_name(s):
    """Chuyển đổi chuỗi thành tên thư mục an toàn."""
    # Chuyển đổi các ký tự Unicode thành ASCII
    s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('ASCII')
    # Chỉ giữ lại ký tự chữ, số, gạch dưới, khoảng trắng, gạch ngang
    s = re.sub(r'[^\w\s-]', '_', s)
    # Thay thế khoảng trắng bằng gạch dưới
    s = re.sub(r'\s+', '_', s)
    return s

def generate_unique_folder_name(base_name):
    """Tạo tên thư mục duy nhất bằng cách thêm timestamp."""
    timestamp = datetime.now().strftime('_%Y%m%d_%H%M%S')
    return f"{base_name}{timestamp}"

# --- CÁC ROUTE VÀ SỰ KIỆN SOCKETIO ---
@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('confirmation_response')
def handle_confirmation(data):
    global state
    if state == "AWAITING_CONFIRMATION":
        if data['response'] == 'yes': state = "WEIGHING"
        else: state = "FAILURE_LEARNING"


@socketio.on('weighing_mock_add')
def handle_weighing_mock():
    if random.choice([True, False]):
        load_cell_1.add_paper_mock(random.uniform(0.1, 0.5))
    else:
        load_cell_2.add_paper_mock(random.uniform(0.1, 0.5))

# --- NHẬN THÔNG TIN NGƯỜI LẠ TỪ WEB ---
unknown_person_info = {}

@socketio.on('unknown_info_submit')
def handle_unknown_info_submit(data):
    """Nhận tên và lớp từ client khi nhận diện sai."""
    global unknown_person_info
    name = data.get('name', '').strip()
    class_name = data.get('class_name', '').strip()
    if name and class_name:
        # Lưu tạm thông tin để sử dụng khi lưu ảnh
        unknown_person_info = {'name': name, 'class': class_name}
        print(f"[WEB] Đã nhận thông tin người lạ: {name} - {class_name}")

# --- HÀM LOGIC CHÍNH ---
def background_thread():
    global state, cap, recognition_start_time, current_transaction_info, manual_trigger, idle_message_printed

    print("-" * 40)
    print("He thong PaperGo Pro da khoi dong.")
    print("Mo trinh duyet va truy cap http://127.0.0.1:5000")
    print("-" * 40)

    while True:
        if state == "IDLE":
            # --- THAY ĐỔI: Chỉ in thông báo một lần duy nhất ---
            if not idle_message_printed:
                print(f"[{time.strftime('%H:%M:%S')}] Trang thai: CHO. Nhan phim 'h' trong CMD de bat dau.")
                idle_message_printed = True
            
            if manual_trigger:
                state = "ACTIVATED"
                manual_trigger = False
                print(f"\n[{time.strftime('%H:%M:%S')}] >> Da kich hoat thu cong! Chuyen sang trang thai KICH HOAT.")
                idle_message_printed = False # Reset lại để lần sau quay về IDLE sẽ in lại
            socketio.sleep(0.5)

        elif state == "ACTIVATED":
            socketio.emit('update_state', {'state': 'recognizing', 'message': 'Xin hãy nhìn thẳng vào camera...'})
            try:
                if cap:  # Nếu camera đã được mở trước đó
                    cap.release()  # Giải phóng camera cũ
                    time.sleep(0.5)  # Chờ camera được giải phóng hoàn toàn
                
                cap = cv2.VideoCapture(config.CAMERA_INDEX)
                if not cap.isOpened():
                    print("!!! LOI: Khong the ket noi voi camera!")
                    raise Exception("Camera không khởi động được")
                
                # Đọc một frame thử để đảm bảo camera hoạt động
                ret, test_frame = cap.read()
                if not ret or test_frame is None:
                    raise Exception("Không thể đọc dữ liệu từ camera")
                
                recognition_start_time = time.time()
                state = "RECOGNIZING"
                print("[CAMERA] Da ket noi thanh cong voi camera")
            except Exception as e:
                print(f"!!! LOI CAMERA: {str(e)}")
                state = "CLEANUP"  # Quay về trạng thái IDLE nếu có lỗi
                if cap:
                    cap.release()
                    cap = None

        elif state == "RECOGNIZING":
            if not cap or not cap.isOpened(): state = "CLEANUP"; continue
            ret, frame = cap.read()
            if not ret: state = "CLEANUP"; continue
            _, buffer = cv2.imencode('.jpg', frame)
            b64_frame = base64.b64encode(buffer).decode('utf-8')
            socketio.emit('update_frame', {'frame': b64_frame})
            result_package = recognizer.recognize(frame)
            if result_package and result_package.get("info"):
                current_transaction_info = result_package["info"]
                state = "AWAITING_CONFIRMATION"
                recognition_start_time = time.time()
            elif time.time() - recognition_start_time > config.RECOGNITION_TIMEOUT_S:
                state = "FAILURE_LEARNING"
            socketio.sleep(0.05)

        elif state == "AWAITING_CONFIRMATION":
            # --- THAY ĐỔI: Gửi thời gian còn lại liên tục ---
            time_left = config.CONFIRMATION_TIMEOUT_S - (time.time() - recognition_start_time)
            socketio.emit('show_confirmation', {
                'name': current_transaction_info['ho_ten'],
                'time_left': int(time_left)
            })
            
            if time_left <= 0:
                state = "CLEANUP"
            socketio.sleep(0.5) # Giảm sleep để cập nhật mượt hơn

        elif state == "FAILURE_LEARNING":
            socketio.emit('update_state', {'state': 'failure_learning'})
            global unknown_person_info
            # --- THAY ĐỔI: CHỜ KHÔNG GIỚI HẠN ---
            while not (unknown_person_info.get('name') and unknown_person_info.get('class')):
                socketio.sleep(0.5)
            print("[MAIN] Da nhan thong tin tu nguoi dung. Tiep tuc xu ly...")
                
            try:
                if unknown_person_info.get('name') and unknown_person_info.get('class'):
                    name_clean = safe_folder_name(unknown_person_info['name'])
                    class_clean = safe_folder_name(unknown_person_info['class'])
                    # Đảm bảo tên thư mục không bị trống
                    if name_clean and class_clean:
                        base_folder_name = f"{name_clean}_{class_clean}"
                    else:
                        base_folder_name = "unknown"
                else:
                    base_folder_name = "unknown"
                    
                # Tạo tên thư mục duy nhất bằng cách thêm timestamp
                folder_name = generate_unique_folder_name(base_folder_name)
                print(f"[DEBUG] Ten thu muc se tao: {folder_name}")
            except Exception as e:
                print(f"[DEBUG] Loi khi tao ten thu muc: {str(e)}")
                folder_name = generate_unique_folder_name("unknown")
            
            unidentified_folder_path = os.path.join(config.UNIDENTIFIED_PATH, folder_name)
            try:
                # Đảm bảo thư mục tồn tại
                os.makedirs(unidentified_folder_path, exist_ok=True)
                
                # Kiểm tra camera còn hoạt động không
                if not cap or not cap.isOpened():
                    print("!!! LOI: Camera khong hoat dong khi chup anh nguoi la!")
                    cap = cv2.VideoCapture(config.CAMERA_INDEX)
                    if not cap.isOpened():
                        raise Exception("Khong the ket noi lai voi camera!")
                    time.sleep(1)  # Chờ camera khởi động

                saved_images = 0
                max_attempts = config.NUM_UNKNOWN_FACES_TO_SAVE * 2  # Số lần thử tối đa
                attempts = 0

                print(f"[DEBUG] Thu muc luu anh: {unidentified_folder_path}")
                print(f"[DEBUG] Kiem tra thu muc ton tai: {os.path.exists(unidentified_folder_path)}")
                print(f"[DEBUG] Kiem tra quyen ghi: {os.access(config.UNIDENTIFIED_PATH, os.W_OK)}")

                while saved_images < config.NUM_UNKNOWN_FACES_TO_SAVE and attempts < max_attempts:
                    print(f"[DEBUG] Lan thu {attempts + 1}: Dang chup anh...")
                    ret, frame = cap.read()
                    if not ret:
                        print("[DEBUG] Khong the doc frame tu camera")
                        attempts += 1
                        continue
                    
                    if frame is None:
                        print("[DEBUG] Frame rong")
                        attempts += 1
                        continue

                    print(f"[DEBUG] Frame size: {frame.shape}")
                    
                    try:
                        # Đảm bảo thư mục tồn tại trước khi lưu
                        if not os.path.exists(unidentified_folder_path):
                            print(f"[DEBUG] Tao lai thu muc: {unidentified_folder_path}")
                            os.makedirs(unidentified_folder_path, exist_ok=True)
                        
                        image_path = os.path.join(unidentified_folder_path, f"face_{saved_images + 1}.jpg")
                        success = cv2.imwrite(image_path, frame)
                        
                        if success and os.path.exists(image_path):
                            saved_images += 1
                            print(f"[AI]: Da luu anh {saved_images}/{config.NUM_UNKNOWN_FACES_TO_SAVE} tai {image_path}")
                        else:
                            print(f"[DEBUG] Khong the luu anh tai: {image_path}")
                    except Exception as e:
                        print(f"[DEBUG] Loi khi luu anh: {str(e)}")
                    
                    attempts += 1
                    socketio.sleep(0.5)  # Tăng delay giữa các lần chụp

                if saved_images == 0:
                    print("!!! LOI: Khong the luu bat ky anh nao!")
                elif saved_images < config.NUM_UNKNOWN_FACES_TO_SAVE:
                    print(f"!!! CANH BAO: Chi luu duoc {saved_images}/{config.NUM_UNKNOWN_FACES_TO_SAVE} anh")
                else:
                    print(f"[AI]: Da luu thanh cong {config.NUM_UNKNOWN_FACES_TO_SAVE} anh vao: {unidentified_folder_path}")
            
            except Exception as e:
                print(f"!!! LOI khi luu anh nguoi la: {str(e)}")
                if os.path.exists(unidentified_folder_path):
                    print(f"Thu muc luu anh: {unidentified_folder_path}")
                    print(f"Noi dung thu muc: {os.listdir(unidentified_folder_path)}")
            
            # Lưu thông tin transaction
            if unknown_person_info.get('name') and unknown_person_info.get('class'):
                # --- LOGIC MỚI: TỰ ĐỘNG TẠO HỌC SINH MỚI ---
                db = SessionLocal()
                try:
                    user_name = unknown_person_info['name']
                    user_class = unknown_person_info['class']

                    # 1. Kiểm tra xem học sinh đã tồn tại chưa
                    student = db.query(Student).filter(Student.name == user_name, Student.class_name == user_class).first()
                    
                    if not student:
                        # 2. Nếu chưa, tạo mới và kích hoạt ngay. CSDL sẽ tự động gán ID mới.
                        print(f"[MAIN] Khong tim thay hoc sinh '{user_name} - {user_class}'. Tu dong tao moi.")
                        student = Student(
                            name=user_name,
                            class_name=user_class,
                            is_active=True # Kích hoạt ngay
                        )
                        db.add(student)
                        db.commit()
                        db.refresh(student)
                        print(f"[MAIN] Da tu dong tao hoc sinh moi: ID={student.id}, Ten={student.name}")

                    # 3. Tạo session tái chế liên kết với học sinh này
                    session_id = data_logger.log_recycling_event(
                        student_id=student.id, ho_ten=student.name, lop=student.class_name,
                        khoi_luong_kg=0, unidentified_folder=folder_name, commit_now=True
                    )
                    current_transaction_info = {"student_id": student.id, "ho_ten": student.name, "lop": student.class_name, "unidentified_folder": folder_name, "session_id": session_id}

                    # 4. Giao nhiệm vụ cho worker
                    learning_task = {
                        "name": student.name, "class_name": student.class_name,
                        "unidentified_folder_path": unidentified_folder_path,
                        "recycle_session_id": session_id
                    }
                    learning_task_queue.put(learning_task)
                    print(f"[MAIN] Da giao nhiem vu hoc cho Worker: {learning_task['name']}")
                except Exception as e:
                    print(f"!!! LOI khi tu dong tao hoc sinh: {e}")
                    db.rollback()
                    current_transaction_info = {"student_id": "UNKNOWN", "ho_ten": "UNKNOWN", "lop": "UNKNOWN", "unidentified_folder": folder_name}
                finally:
                    db.close()
            else:
                current_transaction_info = {"student_id": "UNKNOWN", "ho_ten": "UNKNOWN", "lop": "UNKNOWN", "unidentified_folder": folder_name}
            # Reset lại biến lưu thông tin người lạ
            unknown_person_info = {}
            state = "WEIGHING"

        elif state == "WEIGHING":
            if cap: cap.release(); cap = None
            socketio.emit('update_state', {'state': 'weighing'})

            weight_before_1 = load_cell_1.get_weight()
            weight_before_2 = load_cell_2.get_weight()
            active_bin_index = 0
            paper_weight = 0.0
            weighing_start_time = time.time()

            while time.time() - weighing_start_time < config.WEIGHING_DURATION_S:
                current_weight_1 = load_cell_1.get_weight()
                current_weight_2 = load_cell_2.get_weight()
                added_weight_1 = current_weight_1 - weight_before_1
                added_weight_2 = current_weight_2 - weight_before_2

                if added_weight_1 > added_weight_2 and added_weight_1 > 0.01:
                    active_bin_index = 1
                    paper_weight = added_weight_1
                elif added_weight_2 > added_weight_1 and added_weight_2 > 0.01:
                    active_bin_index = 2
                    paper_weight = added_weight_2
                else:
                    active_bin_index = 0
                    paper_weight = 0.0

                time_left = config.WEIGHING_DURATION_S - (time.time() - weighing_start_time)
                socketio.emit('update_weight', {
                    'weights': {'bin_1': current_weight_1, 'bin_2': current_weight_2},
                    'added_weight': paper_weight, 'time_left': int(time_left)
                })
                socketio.sleep(0.5)

            # --- TÍCH HỢP LOGIC TÍNH ĐIỂM (MỚI) ---
            if paper_weight > 0.01 and active_bin_index != 0:
                print(f"[LOG]: Da ghi nhan {paper_weight:.3f}kg giay vao thung {active_bin_index}.")
                
                student_id = current_transaction_info.get("student_id")
                points_earned = 0
                total_points = 0

                # Nếu là người lạ, chúng ta cập nhật bản ghi session đã tạo trước đó
                if student_id == "UNKNOWN" and "session_id" in current_transaction_info:
                    points_earned, total_points = point_handler.add_points_and_update_session(
                        session_id=current_transaction_info['session_id'],
                        paper_weight_kg=paper_weight
                    )
                else: # Nếu là người đã nhận diện, tạo session mới và cộng điểm
                    points_earned, total_points = point_handler.add_points(student_id, paper_weight)
                    # Ghi log sự kiện
                    data_logger.log_recycling_event(
                        student_id=student_id,
                        ho_ten=current_transaction_info.get("ho_ten"),
                        lop=current_transaction_info.get("lop"),
                        khoi_luong_kg=paper_weight,
                        points_earned=points_earned,
                        unidentified_folder=current_transaction_info.get("unidentified_folder")
                    )

                current_transaction_info["points_earned"] = points_earned
                current_transaction_info["total_points"] = total_points
                print(f"[POINTS] Giao dich hoan tat. Diem nhan duoc: {points_earned}. Tong diem: {total_points}")
                
            current_transaction_info["khoi_luong_kg"] = paper_weight
            state = "THANK_YOU"

        elif state == "THANK_YOU":
            # --- TÙY CHỈNH THÔNG ĐIỆP CẢM ƠN VÀ HIỂN THỊ ĐIỂM ---
            weight_g = current_transaction_info.get("khoi_luong_kg", 0) * 1000
            points_earned = current_transaction_info.get("points_earned", 0)
            total_points = current_transaction_info.get("total_points", 0)
            student_id = current_transaction_info.get("student_id")
            
            if weight_g > 10:
                if student_id and student_id != "UNKNOWN":
                    message = f"Cảm ơn bạn đã tái chế {weight_g:.0f}g giấy! Bạn nhận được {points_earned} điểm!"
                else:
                    message = f"Cảm ơn bạn đã tái chế {weight_g:.0f}g giấy! Hãy đăng ký để tích điểm nhé!"
            else:
                message = "Cảm ơn bạn đã ghé thăm!"

            socketio.emit('show_thankyou', {
                'message': message,
                'points_earned': points_earned,
                'total_points': total_points
            })
            socketio.sleep(5)
            state = "CLEANUP"

        elif state == "CLEANUP":
            try:
                if cap:
                    cap.release()
                    time.sleep(0.5)  # Chờ camera được giải phóng hoàn toàn
                cap = None
            except Exception as e:
                print(f"!!! LOI khi giai phong camera: {str(e)}")
            finally:
                state = "IDLE"
                socketio.emit('update_state', {'state': 'idle'})
                idle_message_printed = False # Reset lại để lần sau quay về IDLE sẽ in lại
# --- KHỞI ĐỘNG HỆ THỐNG ---
if __name__ == '__main__':
    listener_thread = threading.Thread(target=key_listener, daemon=True)
    listener_thread.start()
    learning_worker_thread.start() # <-- KHỞI ĐỘNG WORKER
    socketio.start_background_task(background_thread)
    socketio.run(app, host='0.0.0.0', port=5000)