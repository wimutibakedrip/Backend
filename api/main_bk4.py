# main.py 
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Any
from pydantic import BaseModel

import os
import shutil

from . import models
from .database import SessionLocal, engine, get_db

# สั่งให้ SQLAlchemy สร้างตารางข้อมูลใน PostgreSQL ทันทีที่เปิด Server
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Wimuti Bakery API")

# ปลดล็อก CORS เพื่อให้ React สามารถยิง API มาหา FastAPI ได้
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],
)

# ----------------------------------------------------
# 💡 เปิดให้ภายนอกสามารถเข้ามาดึงรูปภาพในโฟลเดอร์ uploads ไปแสดงผลได้
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/static-images", StaticFiles(directory=UPLOAD_DIR), name="images")

# ----------------------------------------------------
# 🔑 API สำหรับฝั่ง ADMIN: ตรวจสอบรหัสผ่าน Login
# ----------------------------------------------------
class AdminLoginRequest(BaseModel):
    password: str

@app.post("/api/admin/verify-password")
def verify_admin_password(request: AdminLoginRequest):
    CORRECT_PASSWORD = "123456"  
    if request.password != CORRECT_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="รหัสผ่านผู้ดูแลระบบไม่ถูกต้อง!"
        )
    return {"message": "เข้าสู่ระบบสำเร็จ", "authenticated": True}

# ----------------------------------------------------
# 👤 API สำหรับฝั่ง USER & ADMIN: ดึงข้อมูลเมนูทั้งหมด (แก้ไขจุดนี้เพื่อให้ข้อมูลยอมไหลผ่านชัวร์ๆ)
# ----------------------------------------------------
@app.get("/api/products")
def get_all_products(db: Session = Depends(get_db)):
    products = db.query(models.ProductModel).all()
    from fastapi.encoders import jsonable_encoder
    
    # 💡 ใช้ jsonable_encoder แปลงตรงๆ ไม่ผ่าน response_model 
    # เพื่อป้องกันไม่ให้ Pydantic บล็อกข้อมูลกรณีที่มีค่า NULL อยู่ใน PostgreSQL ข้อมูลเก่าจะโชว์ปกติทันที
    return jsonable_encoder(products)

# ----------------------------------------------------
# 🔑 API สำหรับฝั่ง ADMIN: เพิ่มเมนูขนมใหม่ POST พร้อมอัปโหลดรูป
# ----------------------------------------------------
@app.post("/api/products")
async def create_product(
    name: str = Form(...),
    category: str = Form(...),
    price: float = Form(...),
    pieces: int = Form(...),
    desc: str = Form(None),
    file: UploadFile = File(None), 
    db: Session = Depends(get_db)
):
    image_url = "https://unsplash.com"

    if file:
        file_location = f"{UPLOAD_DIR}/{file.filename}"
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        image_url = f"http://localhost:8000/static-images/{file.filename}"

    db_product = models.ProductModel(
        name=name,
        category=category,
        price=price,
        pieces=pieces,
        image=image_url,
        desc=desc if desc else "",
        is_active=True, 
    )    
    try:
        db.add(db_product)
        db.commit()
        db.refresh(db_product)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"เกิดข้อผิดพลาด: {str(e)}")

    from fastapi.encoders import jsonable_encoder
    return {"message": "เพิ่มสินค้าเรียบร้อยแล้ว", "data": jsonable_encoder(db_product)}
   
# ----------------------------------------------------
# 🔑 API สำหรับฝั่ง ADMIN: แก้ไขข้อมูลเมนูและราคา PUT (ปรับปรุงการรับข้อมูลจาก React)
# ----------------------------------------------------
@app.put("/api/products/{product_id}")
def update_product(product_id: int, updated_data: dict, db: Session = Depends(get_db)):
    # 💡 เปลี่ยนประเภทรับข้อมูลจาก models.ProductCreate เป็น dict ตรงๆ เพื่อความยืดหยุ่นสูง
    db_product = db.query(models.ProductModel).filter(models.ProductModel.id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="ไม่พบเมนูสินค้านี้ในระบบ")
    
    # วนลูปอัปเดตฟิลด์ข้อมูลที่ส่งมาจากฟอร์ม React
    for key, value in updated_data.items():
        if hasattr(db_product, key):
            setattr(db_product, key, value)

    try:    
        db.commit()
        db.refresh(db_product)
    except Exception as e:
        db.rollback() 
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"ไม่สามารถบันทึกข้อมูลได้เนื่องจาก: {str(e)}"
        )        
    from fastapi.encoders import jsonable_encoder
    return jsonable_encoder(db_product)

# ----------------------------------------------------
# 🔑 API สำหรับฝั่ง ADMIN: ลบเมนูออกจากระบบ DELETE
# ----------------------------------------------------
@app.delete("/api/products/{product_id}", status_code=status.HTTP_200_OK)
def delete_product(product_id: int, db: Session = Depends(get_db)):
    db_product = db.query(models.ProductModel).filter(models.ProductModel.id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="ไม่พบเมนูสินค้านี้ในระบบ")
    
    db.delete(db_product)
    try:
        db.commit()
    except Exception as e:
        db.rollback() 
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"ไม่สามารถลบข้อมูลได้เนื่องจาก: {str(e)}"
        )
    return {"message": "ลบเมนูเบเกอรี่เรียบร้อยแล้ว"}

# ----------------------------------------------------
# 🔑 API สำหรับฝั่ง ADMIN: สลับสถานะ พร้อมขาย หรือ ยกเลิก PATCH
# ----------------------------------------------------
@app.patch("/api/products/{product_id}/toggle-status")
def toggle_product_status(product_id: int, db: Session = Depends(get_db)):
    db_product = db.query(models.ProductModel).filter(models.ProductModel.id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="ไม่พบเมนูสินค้านี้ในระบบ")
    
    db_product.is_active = not db_product.is_active
    
    try:
        db.commit()
        db.refresh(db_product)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"ไม่สามารถเปลี่ยนสถานะได้: {str(e)}")
        
    from fastapi.encoders import jsonable_encoder
    return {"message": "เปลี่ยนสถานะสินค้าเรียบร้อยแล้ว", "data": jsonable_encoder(db_product)}


# =======================================================================================================
# 🍰 ส่วนที่เพิ่มใหม่: ORDER TRACKING SYSTEM (ระบบติดตามออเดอร์)
# =======================================================================================================

class OrderItemCreate(BaseModel):
    product_id: int
    quantity: int

class OrderCreateRequest(BaseModel):
    items: List[OrderItemCreate]

class OrderStatusUpdateRequest(BaseModel):
    status: str

# 1. API สำหรับฝั่ง USER: ส่งออเดอร์ใหม่เข้ามาในระบบ
@app.post("/api/orders", status_code=status.HTTP_201_CREATED)
def create_order(request: OrderCreateRequest, db: Session = Depends(get_db)):
    total_price = 0.0
    order_items_to_add = []
    
    # วนลูปตรวจสอบสินค้า คำนวณราคารวม และตัดสต็อกสินค้า (pieces)
    for item in request.items:
        product = db.query(models.ProductModel).filter(models.ProductModel.id == item.product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"ไม่พบสินค้าไอดี {item.product_id} ในระบบ")
        
        if not product.is_active:
            raise HTTPException(status_code=400, detail=f"สินค้า {product.name} ถูกปิดใช้งานอยู่ชั่วคราว")
            
        if product.pieces < item.quantity:
            raise HTTPException(
                status_code=400, 
                detail=f"สินค้า {product.name} มีจำนวนไม่พอ (เหลืออยู่ในระบบ {product.pieces} ชิ้น)"
            )
        
        # ตัดสต็อกสินค้า
        product.pieces -= item.quantity
        
        # คำนวณราคารวม ณ ตอนสั่งซื้อ
        item_total_price = product.price * item.quantity
        total_price += item_total_price
        
        # เตรียมอ็อบเจกต์ OrderItem
        order_items_to_add.append(models.OrderItemModel(
            product_id=product.id,
            quantity=item.quantity,
            price=product.price  # บันทึกราคา ณ วันที่ซื้อจริงป้องกันการเปลี่ยนราคาเมนูภายหลัง
        ))
    
    # บันทึกข้อมูลใบออเดอร์หลัก
    db_order = models.OrderModel(
        total_price=total_price,
        status="รอดำเนินการ",  # สถานะเริ่มต้น: รอดำเนินการ, กำลังปรุง/อบ, พร้อมเสิร์ฟ/ส่ง, สำเร็จ, ยกเลิก
        items=order_items_to_add
    )
    
    try:
        db.add(db_order)
        db.commit()
        db.refresh(db_order)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"ไม่สามารถบันทึกออเดอร์ได้เนื่องจาก: {str(e)}")
        
    from fastapi.encoders import jsonable_encoder
    return {"message": "บันทึกออเดอร์ของคุณเรียบร้อยแล้ว", "order": jsonable_encoder(db_order)}


# 2. API สำหรับฝั่ง USER & ADMIN: ดึงรายการออเดอร์ทั้งหมดเพื่อดูสถานะล่าสุด
@app.get("/api/orders")
def get_all_orders(db: Session = Depends(get_db)):
    # ดึงออเดอร์ล่าสุดเรียงจากใหม่ไปเก่า (ออเดอร์เข้าล่าสุดจะอยู่ด้านบนสุด)
    orders = db.query(models.OrderModel).order_by(models.OrderModel.id.desc()).all()
    from fastapi.encoders import jsonable_encoder
    return jsonable_encoder(orders)


# 3. API สำหรับฝั่ง ADMIN: อัปเดตสถานะออเดอร์ (เช่น เปลี่ยนจาก รอดำเนินการ -> กำลังปรุง/อบ)
@app.put("/api/orders/{order_id}/status")
def update_order_status(order_id: int, request: OrderStatusUpdateRequest, db: Session = Depends(get_db)):
    db_order = db.query(models.OrderModel).filter(models.OrderModel.id == order_id).first()
    if not db_order:
        raise HTTPException(status_code=404, detail="ไม่พบรหัสออเดอร์นี้ในระบบ")
        
    # หากมีการปรับสถานะเป็น "ยกเลิก" ให้คืนจำนวนสินค้ากลับเข้าคลังสต็อก (pieces)
    if request.status == "ยกเลิก" and db_order.status != "ยกเลิก":
        for item in db_order.items:
            product = db.query(models.ProductModel).filter(models.ProductModel.id == item.product_id).first()
            if product:
                product.pieces += item.quantity
                
    db_order.status = request.status
    
    try:
        db.commit()
        db.refresh(db_order)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"ไม่สามารถเปลี่ยนสถานะออเดอร์ได้: {str(e)}")
        
    return {"message": "อัปเดตสถานะออเดอร์สำเร็จ", "status": db_order.status}


# ====================================================
# 📊 ส่วนที่เพิ่มใหม่: SALE MANAGEMENT SYSTEM (สรุปรายงานยอดขาย)
# ====================================================

# 4. API สำหรับฝั่ง ADMIN: รายงานยอดขายรวมและสินค้าขายดี (Dashboard Metrics)
@app.get("/api/sales/summary")
def get_sales_summary(db: Session = Depends(get_db)):
    # 4.1 คำนวณรายได้รวมทั้งหมดจากคำสั่งซื้อที่มีสถานะเป็น "สำเร็จ"
    total_revenue = db.query(func.sum(models.OrderModel.total_price))\
                      .filter(models.OrderModel.status == "สำเร็จ")\
                      .scalar() or 0.0
                      
    # 4.2 นับจำนวนออเดอร์ทั้งหมดแยกตามแต่ละประเภทสถานะ (เช่น รอดำเนินการกี่ออเดอร์, สำเร็จกี่ออเดอร์)
    status_counts = db.query(models.OrderModel.status, func.count(models.OrderModel.id))\
                      .group_by(models.OrderModel.status)\
                      .all()
                      
    # 4.3 จัดอันดับ 5 เมนูสินค้าที่ขายดีที่สุดในร้าน (นับจากจำนวนชิ้นรวมในออเดอร์ที่สั่งซื้อสำเร็จ)
    top_selling_products = db.query(
        models.ProductModel.name,
        func.sum(models.OrderItemModel.quantity).label("total_sold_quantity")
    ).join(models.OrderItemModel, models.ProductModel.id == models.OrderItemModel.product_id)\
     .join(models.OrderModel, models.OrderModel.id == models.OrderItemModel.order_id)\
     .filter(models.OrderModel.status == "สำเร็จ")\
     .group_by(models.ProductModel.name)\
     .order_by(func.sum(models.OrderItemModel.quantity).desc())\
     .limit(5)\
     .all()

    # จัดรูปแบบ JSON Mapping เพื่อความง่ายต่อการนำไปกระจายแสดงผลบน Component ของ React
    status_distribution = {status: count for status, count in status_counts}
    
    return {
        "total_revenue": total_revenue,
        "status_distribution": status_distribution,
        "top_products": [{"name": item.name, "quantity": item.total_sold_quantity} for item in top_selling_products]
    }
