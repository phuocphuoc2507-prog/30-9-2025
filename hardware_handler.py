# hardware_handler.py
import serial
import time
import config
import threading

class LoadCell:
    """
    Lớp này quản lý việc giao tiếp với ESP32 để đọc giá trị từ 2 cân.
    Nó sẽ chạy một luồng (thread) riêng để liên tục đọc dữ liệu từ cổng serial.
    """
    def __init__(self, bin_number):
        self.bin_number = bin_number
        # Sử dụng biến toàn cục để chỉ có một kết nối serial duy nhất cho cả 2 đối tượng LoadCell
        if not hasattr(LoadCell, 'serial_connection') or LoadCell.serial_connection is None:
            LoadCell.initialize_serial()

        # Dữ liệu cân nặng được lưu trữ trong biến class để cả 2 đối tượng có thể truy cập
        LoadCell.weights = {1: 0.0, 2: 0.0}

    @classmethod
    def initialize_serial(cls):
        """Khởi tạo kết nối serial và luồng đọc dữ liệu."""
        cls.serial_connection = None
        cls.last_data_received_time = 0
        cls.is_connected = False
        try:
            cls.serial_connection = serial.Serial(config.SERIAL_PORT, config.BAUD_RATE, timeout=2)
            time.sleep(2) # Chờ kết nối ổn định
            if cls.serial_connection.isOpen():
                print(f"[HARDWARE] Da ket noi thanh cong voi ESP32 tai cong {config.SERIAL_PORT}")
                cls.is_connected = True
                # Bắt đầu luồng đọc dữ liệu nền
                cls.reader_thread = threading.Thread(target=cls.read_serial_data, daemon=True)
                cls.reader_thread.start()
            else:
                 print(f"!!! LOI: Khong the mo cong {config.SERIAL_PORT}")
        except serial.SerialException as e:
            print(f"!!! LOI: Khong tim thay ESP32 tai cong {config.SERIAL_PORT}. Kiem tra lai ket noi hoac cau hinh.")
            print(f"   Chi tiet: {e}")
            print("   -> He thong se chay o che do GIA LAP CAN NANG.")

    @classmethod
    def read_serial_data(cls):
        """
        Hàm này chạy liên tục trong một luồng riêng để đọc và phân tích dữ liệu
        từ ESP32.
        """
        while cls.is_connected:
            try:
                if cls.serial_connection and cls.serial_connection.in_waiting > 0:
                    line = cls.serial_connection.readline().decode('utf-8').strip()
                    # Dữ liệu mong đợi: "Can 1: 105.5 g 	 | 	 Can 2: 20.1 g"
                    if "Can 1:" in line and "Can 2:" in line:
                        parts = line.split('|')
                        # Phân tích phần của cân 1
                        weight1_str = parts[0].split(':')[1].replace('g', '').strip()
                        cls.weights[1] = float(weight1_str) / 1000.0 # Đổi từ g sang kg

                        # Phân tích phần của cân 2
                        weight2_str = parts[1].split(':')[1].replace('g', '').strip()
                        cls.weights[2] = float(weight2_str) / 1000.0 # Đổi từ g sang kg
                        
                        cls.last_data_received_time = time.time()
                else:
                    # Nếu không nhận được dữ liệu trong 5 giây, coi như mất kết nối
                    if time.time() - cls.last_data_received_time > 5 and cls.last_data_received_time != 0:
                         print("!!! Canh bao: Mat ket noi voi ESP32 (khong nhan duoc du lieu).")
                         cls.is_connected = False # Dừng vòng lặp
            except Exception as e:
                print(f"!!! LOI trong khi doc du lieu serial: {e}")
                cls.is_connected = False # Dừng vòng lặp
            time.sleep(0.1) # Giảm tải CPU


    def get_weight(self):
        """
        Trả về giá trị cân nặng (kg) đã được đọc từ luồng nền.
        Nếu không có kết nối phần cứng, sẽ trả về giá trị giả lập.
        """
        if self.is_connected:
            return self.weights.get(self.bin_number, 0.0)
        else:
            # --- Chế độ giả lập khi không có phần cứng ---
            if not hasattr(self, 'mock_weight'):
                self.mock_weight = 0.0 # Khởi tạo cân nặng giả lập
            return self.mock_weight

    def add_paper_mock(self, weight_kg):
        """
        Hàm này CHỈ DÙNG CHO VIỆC GIẢ LẬP khi không có phần cứng.
        """
        if not self.is_connected:
            self.mock_weight += weight_kg
            print(f"\n[GIA LAP] Ban vua bo them {weight_kg:.3f} kg giay vao thung {self.bin_number}...")