# models.py
from zoneinfo import ZoneInfo
import datetime
import enum
from sqlalchemy import Column, Integer, String, Float, Text, Boolean, ForeignKey, DateTime, Enum
from sqlalchemy.orm import relationship
from pydantic import BaseModel
from .database import Base 

# ==========================================
# SQLAlchemy Models (ตารางสำหรับ PostgreSQL)
# ==========================================
class ProductModel(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    pieces = Column(Integer, nullable=False)
    image = Column(String, nullable=True)
    desc = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)

class OrderStatus(str, enum.Enum):
    PENDING = "รอดำเนินการ"
    PREPARING = "กำลังปรุง/อบ"
    READY = "พร้อมเสิร์ฟ/ส่ง"
    COMPLETED = "สำเร็จ"
    CANCELLED = "ยกเลิก"

def get_thailand_time():
    return datetime.datetime.now(ZoneInfo("Asia/Bangkok"))

class OrderModel(Base):
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String, nullable=True) 
    subtotal_price = Column(Float, nullable=False, default=0.0)
    discount_price = Column(Float, nullable=False, default=0.0)
    grandtotal_price = Column(Float, nullable=False, default=0.0)
    status = Column(Enum(OrderStatus, native_enum=False), default=OrderStatus.PENDING)
    payment_method = Column(String, nullable=False, default="เงินสด")
    notes = Column(Text, nullable=True)     
    created_at = Column(DateTime(timezone=True), default=get_thailand_time)

    # ความสัมพันธ์เชื่อมต่อไปหา OrderItemModel
    items = relationship("OrderItemModel", back_populates="order", cascade="all, delete-orphan")

    #ALTER TABLE orders ALTER COLUMN created_at TYPE timestamp with time zone;
    #กรณีฟิลย์ created_at ไม่เก็บวันที่เป็น เวลาไทยต้องใช้คำสั่งนี้ ที่ SQL Editer

class OrderItemModel(Base):
    __tablename__ = "order_items"
    
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)  # ราคา ณ วันที่สั่งซื้อ
    
    order = relationship("OrderModel", back_populates="items")
    product = relationship("ProductModel")

# ==========================================
# Pydantic Schemas (สำหรับรับ-ส่งข้อมูลกับ React)
# ==========================================
class ProductCreate(BaseModel):
    name: str
    category: str
    price: float
    pieces: int
    image: str = "https://unsplash.com"
    desc: str = ""
    is_active: bool = True

    # 💡 ย้ายคลาส Config เข้ามาอยู่ในรูปแบบข้อกำหนดของ Pydantic
    class Config:
        from_attributes = True

class ProductResponse(ProductCreate):
    id: int
