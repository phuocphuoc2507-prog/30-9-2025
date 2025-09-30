# models.py
import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import config

# 1. Cấu hình kết nối CSDL
DATABASE_URL = f"sqlite:///{os.path.join(config.DATABASE_PATH, 'papergo.db')}"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 2. Định nghĩa các bảng dưới dạng Class (Models)

class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    class_name = Column("class", String, nullable=False) # Đặt tên cột là 'class'
    total_points = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    # Mối quan hệ: một học sinh có nhiều phiên tái chế
    recycle_sessions = relationship("RecycleSession", back_populates="student")

class RecycleSession(Base):
    __tablename__ = "recycle_sessions"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=True) # Cho phép null cho người lạ
    timestamp = Column(DateTime, default=datetime.utcnow)
    weight_kg = Column(Float, nullable=False)
    points_awarded = Column(Integer, default=0)
    unidentified_folder = Column(String, nullable=True) # Lưu folder ảnh người lạ

    # Mối quan hệ: một phiên thuộc về một học sinh
    student = relationship("Student", back_populates="recycle_sessions")

class FaceAudit(Base):
    __tablename__ = "faces_audit"

    id = Column(Integer, primary_key=True, index=True)
    # Liên kết với phiên tái chế để biết ảnh này từ đâu ra
    recycle_session_id = Column(Integer, ForeignKey("recycle_sessions.id"), nullable=True)
    # Học sinh được gán cho khuôn mặt này
    assigned_student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    # Đường dẫn tới file ảnh gốc trong thư mục unidentified
    source_image_path = Column(String, nullable=False)
    # Đường dẫn tới file ảnh mới trong dataset
    destination_image_path = Column(String, nullable=True)
    # Kết quả QC
    qc_passed = Column(Boolean, default=False)
    status_message = Column(String, nullable=True) # Ghi chú (ví dụ: "Blurry", "Multiple faces")
    timestamp = Column(DateTime, default=datetime.utcnow)

# 3. Hàm khởi tạo CSDL
def init_db():
    """
    Hàm này sẽ được gọi một lần khi chương trình bắt đầu
    để tạo tất cả các bảng trong CSDL nếu chúng chưa tồn tại.
    """
    # Tạo thư mục database nếu chưa có
    os.makedirs(config.DATABASE_PATH, exist_ok=True)
    
    print("[DATABASE] Kiem tra va tao CSDL...")
    try:
        Base.metadata.create_all(bind=engine)
        print("[DATABASE] CSDL da san sang.")
    except Exception as e:
        print(f"!!! LOI khi khoi tao CSDL: {e}")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()