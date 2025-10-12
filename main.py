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
import shutil
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

# --- REFACTOR #1: SỬ DỤNG LỚP ĐỂ QUẢN LÝ TRẠNG THÁI AN TOÀN LUỒNG ---
class SystemState:
    def __init__(self):
        self._lock = threading.Lock()
        self._state = "IDLE"
        self._manual_trigger = False
        self._current_transaction_info = {}
        self._unknown_person_info = {}
        self._recognition_start_time = 0
        self._idle_message_printed = False

    def set(self, **kwargs):
        with self._lock:
            for key, value in kwargs.items():
                setattr(self, f"_{key}", value)

    def get(self, *args):
        with self._lock:
            if len(args) == 1:
                return getattr(self, f"_{args[0]}")
            return tuple(getattr(self, f"_{arg}") for arg in args)

    def get_all(self):
        with self._lock:
            return {
                "state": self._state,
                "manual_trigger": self._manual_trigger,
                "current_transaction_info": self._current_transaction_info.copy(),
                "unknown_person_info": self._unknown_person_info.copy(),
                "recognition_start_time": self._recognition_start_time,
                "idle_message_printed": self._idle_message_printed,
            }

system_state = SystemState()

# --- KHỞI TẠO CÁC THÀNH PHẦN KHÁC ---
load_cell_1 = hardware_handler.LoadCell(bin_number=1)
load_cell_2 = hardware_handler.LoadCell(bin_number=2)
recognizer = FaceRecognizer()

# --- HÀNG ĐỢI VÀ WORKER CHO VIỆC HỌC (MỚI) ---
learning_task_queue = queue.Queue()
learning_worker_thread = LearningWorker(learning_task_queue, recognizer)

# --- HÀM LẮNG NGHE BÀN PHÍM ---
def key_listener():
    while True:
        try:
            keyboard.wait('h')
            if system_state.get("state") == "IDLE":
                print("\n[MANUAL TRIGGER] Da nhan phim 'h'. Kich hoat he thong!")
                system_state.set(manual_trigger=True)
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
    if system_state.get("state") == "AWAITING_CONFIRMATION":
        new_state = "WEIGHING" if data['response'] == 'yes' else "FAILURE_LEARNING"
        system_state.set(state=new_state)



@socketio.on('weighing_mock_add')
def handle_weighing_mock():
    if random.choice([True, False]):
        load_cell_1.add_paper_mock(random.uniform(0.1, 0.5))
    else:
        load_cell_2.add_paper_mock(random.uniform(0.1, 0.5))

# --- NHẬN THÔNG TIN NGƯỜI LẠ TỪ WEB ---
@socketio.on('unknown_info_submit')
def handle_unknown_info_submit(data):
    """Nhận tên và lớp từ client khi nhận diện sai."""
    name = data.get('name', '').strip()
    class_name = data.get('class_name', '').strip()
    if name and class_name:
        system_state.set(unknown_person_info={'name': name, 'class': class_name})
        print(f"[WEB] Đã nhận thông tin người lạ: {name} - {class_name}")

# --- REFACTOR #6: CHIA NHỎ HÀM LOGIC CHÍNH ---

def handle_idle_state():
    idle_message_printed, manual_trigger = system_state.get("idle_message_printed", "manual_trigger")
    if not idle_message_printed:
        print(f"[{time.strftime('%H:%M:%S')}] Trang thai: CHO. Nhan phim 'h' trong CMD de bat dau.")
        system_state.set(idle_message_printed=True)

    if manual_trigger:
        system_state.set(state="ACTIVATED", manual_trigger=False, idle_message_printed=False)
        print(f"\n[{time.strftime('%H:%M:%S')}] >> Da kich hoat thu cong! Chuyen sang trang thai KICH HOAT.")
    socketio.sleep(0.5)

def handle_activated_state():
    socketio.emit('update_state', {'state': 'recognizing', 'message': 'Xin hãy nhìn thẳng vào camera...'})
    system_state.set(recognition_start_time=time.time(), state="RECOGNIZING")

def handle_recognizing_state(cap):
    ret, frame = cap.read()
    if not ret:
        system_state.set(state="CLEANUP")
        return

    _, buffer = cv2.imencode('.jpg', frame)
    b64_frame = base64.b64encode(buffer).decode('utf-8')
    socketio.emit('update_frame', {'frame': b64_frame})

    result_package = recognizer.recognize(frame)
    recognition_start_time = system_state.get("recognition_start_time")

    if result_package and result_package.get("info"):
        system_state.set(
            current_transaction_info=result_package["info"],
            state="AWAITING_CONFIRMATION",
            recognition_start_time=time.time() # Reset timer for confirmation
        )
    elif time.time() - recognition_start_time > config.RECOGNITION_TIMEOUT_S:
        system_state.set(state="FAILURE_LEARNING")

    socketio.sleep(0.05)

def handle_awaiting_confirmation_state():
    start_time, trans_info = system_state.get("recognition_start_time", "current_transaction_info")
    time_left = config.CONFIRMATION_TIMEOUT_S - (time.time() - start_time)

    socketio.emit('show_confirmation', {
        'name': trans_info.get('ho_ten', 'N/A'),
        'time_left': int(time_left)
    })

    if time_left <= 0:
        print("[TIMEOUT] Nguoi dung khong xac nhan.")
        system_state.set(state="CLEANUP")

    socketio.sleep(0.5)

def handle_failure_learning_state(cap):
    socketio.emit('update_state', {'state': 'failure_learning'})
    system_state.set(unknown_person_info={}) # Reset info

    # --- REFACTOR #3: THÊM TIMEOUT CHO VÒNG LẶP CHỜ ---
    wait_start_time = time.time()
    user_info = {}
    while time.time() - wait_start_time < config.LEARNING_INPUT_TIMEOUT_S:
        # Gửi thời gian còn lại về cho client
        time_left = config.LEARNING_INPUT_TIMEOUT_S - (time.time() - wait_start_time)
        socketio.emit('update_learning_timer', {'time_left': int(time_left)})

        user_info = system_state.get("unknown_person_info")
        if user_info.get('name') and user_info.get('class'):
            print("[MAIN] Da nhan thong tin tu nguoi dung. Tiep tuc xu ly...")
            break
        # Thay đổi sleep thành 1 giây để khớp với việc cập nhật timer
        socketio.sleep(1)
    else: # Chạy khi vòng lặp kết thúc mà không break (do timeout)
        print(f"[TIMEOUT] Khong nhan duoc thong tin nguoi dung sau {config.LEARNING_INPUT_TIMEOUT_S} giay.")
        system_state.set(state="CLEANUP")
        return # Thoát khỏi hàm này

    # Tạo thư mục để lưu ảnh
    name_clean = safe_folder_name(user_info['name'])
    class_clean = safe_folder_name(user_info['class'])
    base_folder_name = f"{name_clean}_{class_clean}" if name_clean and class_clean else "unknown"
    folder_name = generate_unique_folder_name(base_folder_name)
    unidentified_folder_path = os.path.join(config.UNIDENTIFIED_PATH, folder_name)

    try:
        os.makedirs(unidentified_folder_path, exist_ok=True)
        # Chụp và lưu ảnh
        saved_images = save_unknown_faces(cap, unidentified_folder_path)
        if saved_images == 0:
            raise Exception("Khong the luu bat ky anh nao.")

        # Giao nhiệm vụ cho worker
        process_unknown_user_transaction(user_info, folder_name, unidentified_folder_path)

    except Exception as e:
        print(f"!!! LOI trong qua trinh hoc nguoi la: {e}")
        # Dọn dẹp thư mục nếu có lỗi
        if os.path.exists(unidentified_folder_path):
            shutil.rmtree(unidentified_folder_path)
        system_state.set(state="CLEANUP")
        return

    system_state.set(state="WEIGHING", unknown_person_info={})

def save_unknown_faces(cap, folder_path):
    """Chụp và lưu một số lượng ảnh nhất định vào thư mục chỉ định."""
    saved_count = 0
    max_attempts = config.NUM_UNKNOWN_FACES_TO_SAVE * 2
    for _ in range(max_attempts):
        if saved_count >= config.NUM_UNKNOWN_FACES_TO_SAVE:
            break
        ret, frame = cap.read()
        if not ret or frame is None:
            socketio.sleep(0.2)
            continue

        try:
            image_path = os.path.join(folder_path, f"face_{saved_count + 1}.jpg")
            success = cv2.imwrite(image_path, frame)
            if success:
                saved_count += 1
                print(f"[AI]: Da luu anh {saved_count}/{config.NUM_UNKNOWN_FACES_TO_SAVE} tai {image_path}")
        except Exception as e:
            print(f"!!! LOI khi luu anh nguoi la: {e}")
        socketio.sleep(0.5) # Delay giữa các lần chụp
    return saved_count

def process_unknown_user_transaction(user_info, folder_name, unidentified_folder_path):
    """Tạo học sinh mới (nếu cần), tạo session và giao nhiệm vụ cho worker."""
    db = SessionLocal()
    try:
        user_name = user_info['name']
        user_class = user_info['class']

        student = db.query(Student).filter(Student.name == user_name, Student.class_name == user_class).first()
        if not student:
            print(f"[MAIN] Khong tim thay hoc sinh '{user_name} - {user_class}'. Tu dong tao moi.")
            student = Student(name=user_name, class_name=user_class, is_active=True)
            db.add(student)
            db.commit()
            db.refresh(student)
            print(f"[MAIN] Da tu dong tao hoc sinh moi: ID={student.id}, Ten={student.name}")

        session_id = data_logger.log_recycling_event(
            student_id=student.id, ho_ten=student.name, lop=student.class_name,
            khoi_luong_kg=0, unidentified_folder=folder_name, commit_now=True
        )

        trans_info = {"student_id": student.id, "ho_ten": student.name, "lop": student.class_name, "unidentified_folder": folder_name, "session_id": session_id}
        system_state.set(current_transaction_info=trans_info)

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
        trans_info = {"student_id": "UNKNOWN", "ho_ten": "UNKNOWN", "lop": "UNKNOWN", "unidentified_folder": folder_name}
        system_state.set(current_transaction_info=trans_info)
    finally:
        db.close()

def handle_weighing_state():
    socketio.emit('update_state', {'state': 'weighing'})

    weight_before_1 = load_cell_1.get_weight()
    weight_before_2 = load_cell_2.get_weight()
    paper_weight = 0.0
    weighing_start_time = time.time()

    while time.time() - weighing_start_time < config.WEIGHING_DURATION_S:
        current_weight_1 = load_cell_1.get_weight()
        current_weight_2 = load_cell_2.get_weight()
        added_weight_1 = current_weight_1 - weight_before_1
        added_weight_2 = current_weight_2 - weight_before_2

        if added_weight_1 > added_weight_2 and added_weight_1 > config.MIN_WEIGHT_THRESHOLD_KG:
            paper_weight = added_weight_1
        elif added_weight_2 > added_weight_1 and added_weight_2 > config.MIN_WEIGHT_THRESHOLD_KG:
            paper_weight = added_weight_2
        else:
            paper_weight = 0.0

        time_left = config.WEIGHING_DURATION_S - (time.time() - weighing_start_time)
        socketio.emit('update_weight', {
            'weights': {'bin_1': current_weight_1, 'bin_2': current_weight_2},
            'added_weight': paper_weight, 'time_left': int(time_left)
        })
        socketio.sleep(0.5)

    # Xử lý kết quả cân
    current_transaction_info = system_state.get("current_transaction_info")
    if paper_weight > config.MIN_WEIGHT_THRESHOLD_KG:
        print(f"[LOG]: Da ghi nhan {paper_weight:.3f}kg giay.")
        student_id = current_transaction_info.get("student_id")
        points_earned = 0
        total_points = 0

        if student_id == "UNKNOWN" and "session_id" in current_transaction_info:
            points_earned, total_points = point_handler.add_points_and_update_session(
                session_id=current_transaction_info['session_id'],
                paper_weight_kg=paper_weight
            )
        else:
            points_earned, total_points = point_handler.add_points(student_id, paper_weight)

        current_transaction_info["points_earned"] = points_earned
        current_transaction_info["total_points"] = total_points
        print(f"[POINTS] Giao dich hoan tat. Diem nhan duoc: {points_earned}. Tong diem: {total_points}")

    current_transaction_info["khoi_luong_kg"] = paper_weight
    system_state.set(current_transaction_info=current_transaction_info, state="THANK_YOU")

def handle_thank_you_state():
    current_transaction_info = system_state.get("current_transaction_info")
    weight_g = current_transaction_info.get("khoi_luong_kg", 0) * 1000
    points_earned = current_transaction_info.get("points_earned", 0)
    total_points = current_transaction_info.get("total_points", 0)
    student_id = current_transaction_info.get("student_id")

    if weight_g > 10:
        if student_id and student_id != "UNKNOWN":
            message = f"Cảm ơn bạn đã tái chế {weight_g:.0f}g giấy! Bạn nhận được {points_earned} điểm!"
        else:
            message = f"Cảm ơn bạn đã tái chế {weight_g:.0f}g giấy! Điểm sẽ được cộng sau khi xác thực."
    else:
        message = "Cảm ơn bạn đã ghé thăm!"

    socketio.emit('show_thankyou', {
        'message': message,
        'points_earned': points_earned,
        'total_points': total_points
    })
    socketio.sleep(5)
    system_state.set(state="CLEANUP")

def handle_cleanup_state():
    system_state.set(state="IDLE", idle_message_printed=False, current_transaction_info={})
    socketio.emit('update_state', {'state': 'idle'})

# --- HÀM LOGIC CHÍNH (VÒNG LẶP) ---
def background_thread():
    print("-" * 40)
    print("He thong PaperGo Pro da khoi dong.")
    print("Mo trinh duyet va truy cap http://127.0.0.1:5000")
    print("-" * 40)

    cap = None
    while True:
        state = system_state.get("state")
        # --- REFACTOR #4: QUẢN LÝ CAMERA AN TOÀN VỚI TRY...FINALLY ---
        try:
            # Khởi tạo camera khi cần
            if state in ["RECOGNIZING", "FAILURE_LEARNING"] and (not cap or not cap.isOpened()):
                cap = cv2.VideoCapture(config.CAMERA_INDEX)
                if not cap.isOpened():
                    print("!!! LOI: Khong the ket noi voi camera!")
                    system_state.set(state="CLEANUP")
                    continue
                print("[CAMERA] Da ket noi thanh cong voi camera.")

            # Logic cho từng trạng thái
            if state == "IDLE":
                handle_idle_state()
            elif state == "ACTIVATED":
                handle_activated_state()
            elif state == "RECOGNIZING":
                handle_recognizing_state(cap)
            elif state == "AWAITING_CONFIRMATION":
                handle_awaiting_confirmation_state()
            elif state == "FAILURE_LEARNING":
                handle_failure_learning_state(cap)
            elif state == "WEIGHING":
                handle_weighing_state()
            elif state == "THANK_YOU":
                handle_thank_you_state()
            elif state == "CLEANUP":
                handle_cleanup_state()

        except Exception as e:
            print(f"!!! LOI KHONG XAC DINH trong vong lap chinh: {e}")
            import traceback
            traceback.print_exc()
            system_state.set(state="CLEANUP")

        finally:
            # Giải phóng camera nếu không còn cần thiết
            next_state = system_state.get("state")
            if cap and next_state not in ["RECOGNIZING", "FAILURE_LEARNING"]:
                print("[CAMERA] Giai phong camera.")
                cap.release()
                cap = None


        # --- LOGIC CŨ ---
        # ... (toàn bộ logic if/elif cũ đã được chuyển vào các hàm handle_..._state)
        # ...

        # elif state == "FAILURE_LEARNING":
            # Lưu thông tin transaction
# --- KHỞI ĐỘNG HỆ THỐNG ---
if __name__ == '__main__':
    listener_thread = threading.Thread(target=key_listener, daemon=True)
    listener_thread.start()
    learning_worker_thread.start() # <-- KHỞI ĐỘNG WORKER
    socketio.start_background_task(background_thread)
    socketio.run(app, host='0.0.0.0', port=5000)