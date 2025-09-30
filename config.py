# config.py

# --- Cấu hình Camera & AI ---
CAMERA_INDEX = 0
MODEL_NAME = "ArcFace"
RECOGNITION_THRESHOLD = 1.0
DETECTOR_BACKEND = 'mtcnn'

# --- Cấu hình Logic hệ thống ---
PROXIMITY_THRESHOLD_CM = 100
RECOGNITION_TIMEOUT_S = 15
CONFIRMATION_TIMEOUT_S = 10
NUM_UNKNOWN_FACES_TO_SAVE = 5
WEIGHING_DURATION_S = 15 # Thời gian (giây) cho phép bỏ giấy

# --- Cấu hình Thùng rác & Cân ---
BIN_CAPACITY_KG = 10.0

# --- CẤU HÌNH PHẦN CỨNG (MỚI) ---
SERIAL_PORT = 'COM4'  # QUAN TRỌNG: Thay 'COM4' bằng cổng COM thật của ESP32
BAUD_RATE = 115200

# --- Cấu hình Hệ thống Điểm thưởng (MỚI) ---
POINTS_PER_GRAM = 1 # 1 gram = 1 điểm

# --- Đường dẫn File ---
import os

# Đường dẫn gốc của dự án
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# Các đường dẫn con được tính từ thư mục gốc
DATASET_PATH = os.path.join(PROJECT_ROOT, "dataset")
DATABASE_PATH = os.path.join(PROJECT_ROOT, "database")
METADATA_FILE = os.path.join(PROJECT_ROOT, "metadata.csv")
RECYCLING_LOG_FILE = os.path.join(PROJECT_ROOT, "recycling_log.csv")
UNIDENTIFIED_PATH = os.path.join(PROJECT_ROOT, "unidentified")
USER_DATA_FILE = os.path.join(DATABASE_PATH, "user_data.csv") # ĐƯỜNG DẪN FILE ĐIỂM