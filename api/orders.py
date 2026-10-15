# orders.py
from sqlalchemy import Column, Integer, String, Float, Text, Boolean, DateTime
from pydantic import BaseModel
from .database import Base

# ==========================================
# 1. SQLAlchemy Model (สำหรับสร้างตารางใน PostgreSQL)
# ==========================================
class Orders(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    pieces = Column(Integer, nullable=False)
    image = Column(String, nullable=True)
    desc = Column(Text, nullable=True)
    is_active = Column(Boolean , default=True)

# ==========================================
# SQLAlchemy Model (สำหรับสร้างตารางใน PostgreSQL)
# ==========================================
class OrderItems(Base):
    __tablename__ = "orderitems"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    pieces = Column(Integer, nullable=False)
    image = Column(String, nullable=True)
    desc = Column(Text, nullable=True)
    is_active = Column(Boolean , default=True)

# ==========================================
# 2. Pydantic Schemas (สำหรับตรวจสอบข้อมูลที่ส่งมาจาก React)
# ==========================================
class OrderCreate(BaseModel):
    name: str
    category: str
    price: float
    pieces: int
    image: str = "https://unsplash.com"
    desc: str = ""
    is_active: bool = True

class Config:
    from_attributes = True

class ProductResponse(OrderCreate):
    id: int
