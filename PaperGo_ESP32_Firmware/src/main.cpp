/*
 * Code demo đã được nâng cấp để chạy 2 cân Loadcell đồng thời.
 * Dựa trên code gốc của Rui Santos / bogde.
**/
#include <Arduino.h>
#include "HX711.h"
// #include "soc/rtc.h" // Các dòng rtc... đã được loại bỏ để đảm bảo tương thích

// --- THAY ĐỔI: Định nghĩa chân cho cả 2 cân ---
const int LOADCELL1_DOUT_PIN = 16;
const int LOADCELL1_SCK_PIN = 4;

const int LOADCELL2_DOUT_PIN = 17;
const int LOADCELL2_SCK_PIN = 5;

// --- THAY ĐỔI: Tạo 2 đối tượng scale ---
HX711 scale1;
HX711 scale2;

// --- QUAN TRỌNG: HỆ SỐ HIỆU CHỈNH ---
// Bạn cần tìm ra 2 hệ số này bằng code hiệu chỉnh ở lần chat trước,
// sau đó điền chúng vào đây.
// Đây chỉ là các giá trị ví dụ.
float calibration_factor_1 = 204.3; // THAY SỐ NÀY CHO CÂN 1
float calibration_factor_2 = 208.5; // THAY SỐ NÀY CHO CÂN 2

void setup() {
  Serial.begin(115200);
  Serial.println("Khoi dong chuong trinh doc 2 can LoadCell...");
  
  // --- THAY ĐỔI: Cài đặt cho Cân 1 ---
  Serial.println("Khoi tao Can 1...");
  scale1.begin(LOADCELL1_DOUT_PIN, LOADCELL1_SCK_PIN);
  scale1.set_scale(calibration_factor_1);
  scale1.tare(); // Reset cân 1 về 0
  Serial.println("Can 1 san sang.");

  // --- THAY ĐỔI: Cài đặt cho Cân 2 ---
  Serial.println("Khoi tao Can 2...");
  scale2.begin(LOADCELL2_DOUT_PIN, LOADCELL2_SCK_PIN);
  scale2.set_scale(calibration_factor_2);
  scale2.tare(); // Reset cân 2 về 0
  Serial.println("Can 2 san sang.");
  
  Serial.println("------------------------------------");
}

void loop() {
  // --- THAY ĐỔI: Đọc và in giá trị từ cả 2 cân ---
  Serial.print("Can 1: ");
  // Lấy giá trị khối lượng (đơn vị gram), làm tròn đến 1 chữ số thập phân
  Serial.print(scale1.get_units(5), 1); 
  Serial.print(" g");
  
  Serial.print("\t | \t"); // Dấu phân cách cho dễ nhìn

  Serial.print("Can 2: ");
  Serial.print(scale2.get_units(5), 1);
  Serial.println(" g");
  
  // Bạn có thể giữ hoặc bỏ các dòng power_down/power_up tùy theo nhu cầu
  // scale1.power_down();
  // scale2.power_down();
  delay(1000); // Đợi 1 giây giữa các lần đọc
  // scale1.power_up();
  // scale2.power_up();
}