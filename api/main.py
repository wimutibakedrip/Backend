# main.py 
from zoneinfo import ZoneInfo
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException, status, Query
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Any, Optional
from pydantic import BaseModel

import os
import datetime
import time
import shutil

from . import models
from .database import SessionLocal, engine, get_db
from sqlalchemy.orm import joinedload

# สร้างตารางข้อมูลใน PostgreSQL ทันทีที่เปิด Server
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Wimuti Bakery API")

origins =[
    "http://localhost:5173",
    "https://bakery-frontend-wimuti.vercel.app/",
    "*"
]

# ปลดล็อก CORS เพื่อให้ React สามารถยิง API มาหา FastAPI ได้
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],
)

# ----------------------------------------------------
# เปิดให้ภายนอกสามารถเข้ามาดึงรูปภาพในโฟลเดอร์ uploads ไปแสดงผลได้
UPLOAD_DIR = "uploads"
# os.makedirs(UPLOAD_DIR, exist_ok=True)
# ตรวจสอบคำสั่ง app.mount ให้พาร์ทและชื่อไดเรกทอรีตรงกันเป๊ะๆ
app.mount("/static-images", StaticFiles(directory=UPLOAD_DIR), name="static-images")
# ----------------------------------------------------
# สำหรับฝั่ง ADMIN: ตรวจสอบรหัสผ่าน Login
# ----------------------------------------------------
class AdminLoginRequest(BaseModel):
    password: str

# สำหรับฝั่ง ADMIN: รหัสผ่าน Password ----------------------------------------------
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
    
    # ใช้ jsonable_encoder แปลงตรงๆ ไม่ผ่าน response_model 
    # เพื่อป้องกันไม่ให้ Pydantic บล็อกข้อมูลกรณีที่มีค่า NULL อยู่ใน PostgreSQL ข้อมูลเก่าจะโชว์ปกติทันที
    return jsonable_encoder(products)

# ----------------------------------------------------
# API สำหรับฝั่ง ADMIN: เพิ่มเมนูขนมใหม่ POST พร้อมอัปโหลดรูป
# ----------------------------------------------------
@app.post("/api/products")
async def create_product(
    name: str = Form(...),
    category: str = Form(...),
    price: float = Form(...),
    pieces: int = Form(...),
    image: str = Form("https://unsplash.com"),
    desc: str = Form(None),
    file: UploadFile = File(None), 
    db: Session = Depends(get_db)
):
    image_url = image

    # จุดแก้ไขบั๊กหลังบ้าน: ถ้าหากมีการอัปโหลดไฟล์รูปถ่ายสดมาจากเครื่องคอมพิวเตอร์จริง
    if file and file.filename:
        # รีเซ็ตตำแหน่งข้อมูลไฟล์ (File Pointer) กลับมาที่จุดเริ่มต้น เพื่อให้แน่ใจว่าอ่านข้อมูลได้ครบถ้วน
        await file.seek(0)
        
        # บังคับตั้งชื่อไฟล์ให้ปลอดภัย ป้องกันบั๊กชื่อซ้ำหรือภาษาไทยหลุดพาร์ท
        clean_filename = f"{int(time.time())}_{file.filename.replace(' ', '_')}"
        file_location = f"{UPLOAD_DIR}/{clean_filename}"
        
        # ดำเนินการเปิดและก๊อปปี้เขียนข้อมูลลงสู่โฟลเดอร์ uploads
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # สร้างพาร์ทลิงก์เรียกรูปภาพส่งคืนกลับไปหาฝั่ง React
        image_url = f"https://bakery-backend-wimuti.vercel.app/static-images/{clean_filename}"

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
# API สำหรับฝั่ง ADMIN: แก้ไขข้อมูลเมนูและราคา PUT (ปรับปรุงการรับข้อมูลจาก React)
# ----------------------------------------------------
@app.put("/api/products/{product_id}")
async def update_product(
    product_id: int,
    name: str = Form(...),
    category: str = Form(...),
    price: float = Form(...),
    pieces: int = Form(...),
    image: str = Form("https://unsplash.com"),
    desc: str = Form(None),
    file: UploadFile = File(None), 
    db: Session = Depends(get_db)
):
    image_url = image

    # จุดแก้ไขบั๊กหลังบ้าน: ถ้าหากมีการอัปโหลดไฟล์รูปถ่ายสดมาจากเครื่องคอมพิวเตอร์จริง
    if file and file.filename:
        # รีเซ็ตตำแหน่งข้อมูลไฟล์ (File Pointer) กลับมาที่จุดเริ่มต้น เพื่อให้แน่ใจว่าอ่านข้อมูลได้ครบถ้วน
        await file.seek(0)
        
        # บังคับตั้งชื่อไฟล์ให้ปลอดภัย ป้องกันบั๊กชื่อซ้ำหรือภาษาไทยหลุดพาร์ท
        clean_filename = f"{int(time.time())}_{file.filename.replace(' ', '_')}"
        file_location = f"{UPLOAD_DIR}/{clean_filename}"
        
        # ดำเนินการเปิดและก๊อปปี้เขียนข้อมูลลงสู่โฟลเดอร์ uploads
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # สร้างพาร์ทลิงก์เรียกรูปภาพส่งคืนกลับไปหาฝั่ง React
        image_url = f"http://localhost:8000/static-images/{clean_filename}"

    db_product = db.query(models.ProductModel).filter(models.ProductModel.id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="ไม่พบเมนูสินค้านี้ในระบบ")
    
    # จัดการรูปภาพ: ถ้าแอดมินมีการอัปโหลดไฟล์ภาพชิ้นใหม่เข้ามาสดๆ
    image_url = image
    if file and file.filename:
        await file.seek(0)
        clean_filename = f"{int(time.time())}_{file.filename.replace(' ', '_')}"
        file_location = f"{UPLOAD_DIR}/{clean_filename}"
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        image_url = f"http://localhost:8000/static-images/{clean_filename}"

    # อัปเดตข้อมูลชุดใหม่ลงฟิลด์ต่างๆ ของตารางสินค้า
    db_product.name = name
    db_product.category = category
    db_product.price = price
    db_product.pieces = pieces
    db_product.desc = desc if desc else ""
    db_product.image = image_url

    try:    
        db.commit()
        db.refresh(db_product)
    except Exception as e:
        db.rollback() 
        raise HTTPException(
            status_code=400, 
            detail=f"ไม่สามารถบันทึกข้อมูลแก้ไขได้เนื่องจาก: {str(e)}"
        )        
        
    from fastapi.encoders import jsonable_encoder
    return jsonable_encoder(db_product)

# ----------------------------------------------------
# API สำหรับฝั่ง ADMIN: ลบเมนูออกจากระบบ DELETE
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
# API สำหรับฝั่ง ADMIN: สลับสถานะ พร้อมขาย หรือ ยกเลิก PATCH
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
# ส่วนที่เพิ่มใหม่: ORDER TRACKING SYSTEM (ระบบติดตามออเดอร์)
# =======================================================================================================
class OrderItemCreate(BaseModel):
    product_id: int
    quantity: int

class OrderCreateRequest(BaseModel):
    items: List[OrderItemCreate]
    customer_name: str = ""
    notes: str = ""    
    discount_price: float = 0.0

class OrderStatusUpdateRequest(BaseModel):
    status: str

# API สำหรับฝั่ง USER: ส่งออเดอร์ใหม่เข้ามาในระบบ
@app.post("/api/orders", status_code=status.HTTP_201_CREATED)
def create_order(request: OrderCreateRequest, db: Session = Depends(get_db)):
    subtotal_price = 0.0
    order_items_to_add = []
    
    # วนลูปเช็คสินค้าทีละชิ้น คำนวณราคาจริงตามจริง และทำการหักสต็อกในคลัง
    for req_item in request.items:
        product = db.query(models.ProductModel).filter(models.ProductModel.id == req_item.product_id).first()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"ไม่พบสินค้าไอดี #{req_item.product_id} ในระบบเมนู"
            )
            
        # ตรวจสอบสต็อกคงเหลือ (ฟิลด์ pieces ในดาต้าเบส)
        if product.pieces < req_item.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"สินค้า '{product.name}' มีสต็อกไม่เพียงพอ (เหลือ {product.pieces} ชิ้น แต่สั่งซื้อ {req_item.quantity} ชิ้น)"
            )
            
        # คำนวณราคารวมก่อนหักส่วนลด
        item_total_price = product.price * req_item.quantity
        subtotal_price += item_total_price
        
        # หักจำนวนสินค้าออกจากคลังของร้านเบเกอรี่ทันที
        product.pieces -= req_item.quantity
        
        # แพ็กข้อมูลรายการสินค้าลงใน Model เตรียมบันทึก
        order_item = models.OrderItemModel(
            product_id=product.id,
            quantity=req_item.quantity,
            price=product.price # บันทึกราคา ณ วันที่ซื้อจริงเพื่อป้องกันบั๊กเวลาร้านปรับราคาภายหลัง
        )
        order_items_to_add.append(order_item)

    # 2. คำนวณยอดเงินสุทธิสุทธิ (Grand Total)
    discount_amount = request.discount_price
    grandtotal_price = subtotal_price - discount_amount
    if grandtotal_price < 0: 
        grandtotal_price = 0.0 # ป้องกันบิลติดลบกรณีใส่ส่วนลดเกินราคาจริง

    # 3. สร้างออเดอร์หลักบันทึกลง PostgreSQL
    new_order = models.OrderModel(
        customer_name=request.customer_name,
        subtotal_price=subtotal_price,
        discount_price=discount_amount,
        grandtotal_price=grandtotal_price,
        status=models.OrderStatus.PENDING, # ใช้ Enum จาก models.py ดักค่าเริ่มต้น
        notes=request.notes,
        items=order_items_to_add
    )
    
    try:
        db.add(new_order)
        db.commit()
        db.refresh(new_order)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาดในการบันทึกออเดอร์: {str(e)}")
        
    from fastapi.encoders import jsonable_encoder
    return {"message": "ส่งรายการสั่งซื้อสำเร็จ", "order_id": new_order.id, "data": jsonable_encoder(new_order)}


# ฟังก์ชันดึงออเดอร์คิวครัว
@app.get("/api/orders")
def get_all_orders(
    selected_date: Optional[str] = Query(None, description="รูปแบบวันที่: YYYY-MM-DD"), 
    db: Session = Depends(get_db)):
 
    if selected_date:
        target_date = datetime.datetime.strptime(selected_date, "%Y-%m-%d").date()
    else:
        target_date = datetime.datetime.now(ZoneInfo("Asia/Bangkok")).date()

    # ตั้งเงื่อนไขกรองวันที่โดยแปลงเขตเวลาของฐานข้อมูล (UTC) ให้สัมพันธ์เป็นเวลาไทยปัจจุบัน
    date_filter = func.date(func.timezone('Asia/Bangkok', models.OrderModel.created_at)) == func.date(func.timezone('Asia/Bangkok', target_date))

    orders = db.query(models.OrderModel)\
                .options(
                    joinedload(models.OrderModel.items)
                    .joinedload(models.OrderItemModel.product)
                )\
                .filter(date_filter)\
                .order_by(models.OrderModel.created_at.desc())\
                .all()
               
    # ปรับการ Encode: บังคับแกะโครงสร้าง Object ความสัมพันธ์เชิงลึก (Deep Relationship) 
    # ออกมาเป็น Python Dictionary ดิบ ก่อนแปลงผ่าน jsonable_encoder ป้องกันข้อมูลตารางลูกหาย
    result = []
    for order in orders:
        order_dict = {
            "id": order.id,
            "customer_name": order.customer_name,
            "subtotal_price": order.subtotal_price,
            "discount_price": order.discount_price,
            "grandtotal_price": order.grandtotal_price,
            "status": order.status.value if hasattr(order.status, 'value') else order.status,
            "notes": order.notes,
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "items": []  # สร้างอาเรย์รองรับรายการตารางลูก
        }
        
        # วนลูปแกะข้อมูล order_items และดึงข้อมูลสินค้าจากตาราง product พ่วงออกไปด้วยตรง ๆ
        for item in order.items:
            item_dict = {
                "id": item.id,
                "product_id": item.product_id,
                "quantity": item.quantity,
                "price": item.price,
                "product": {
                    "id": item.product.id if item.product else None,
                    "name": item.product.name if item.product else "🍰 เมนูถูกนำออกจากระบบ",
                    "price": item.product.price if item.product else 0
                } if item.product else None
            }
            order_dict["items"].append(item_dict)
            
        result.append(order_dict)

    from fastapi.encoders import jsonable_encoder
    return jsonable_encoder(result)


# API สำหรับฝั่ง ADMIN: อัปเดตสถานะออเดอร์ (เช่น เปลี่ยนจาก รอดำเนินการ -> กำลังปรุง/อบ)
@app.put("/api/orders/{order_id}/status")
def update_order_status(order_id: int, request: OrderStatusUpdateRequest, db: Session = Depends(get_db)):
    order = db.query(models.OrderModel).filter(models.OrderModel.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="ไม่พบรายการออเดอร์นี้ในคิวห้องครัว")
    
    # ดักตรรกะแปลงจาก String หน้าฟรอนต์เอนด์ไปเป็นรูปแบบ Enum Object ที่ PostgreSQL รองรับ
    matched_status = None
    for enum_item in models.OrderStatus:
        if enum_item.value == request.status:
            matched_status = enum_item
            break
            
    if not matched_status:
        raise HTTPException(status_code=422, detail=f"สถานะ '{request.status}' ไม่สอดคล้องกับระเบียบในระบบร้าน")
        
    order.status = matched_status
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"ไม่สามารถเปลี่ยนสถานะได้: {str(e)}")
        
    return {"message": "อัปเดตคิวขนมเรียบร้อย", "new_status": order.status.value}

# ====================================================
# ส่วนที่เพิ่มใหม่: Order Details (Popup Windows)
# ====================================================
@app.get("/api/orders")
def get_orders(db: Session = Depends(get_db)):
    # ใช้ joinedload บังคับดึงข้อมูลของตาราง order_items (items) และดึงรายละเอียดชื่อขนมของตาราง products (product) ติดไปด้วยพร้อมกัน
    orders = db.query(models.OrderModel)\
               .options(
                   joinedload(models.OrderModel.items)\
                   .joinedload(models.OrderItemModel.product))\
               .order_by(models.OrderModel.created_at.desc())\
               .all()
               
    from fastapi.encoders import jsonable_encoder
    return jsonable_encoder(orders)

# ====================================================
# ส่วนที่เพิ่มใหม่: SALE MANAGEMENT SYSTEM (สรุปรายงานยอดขาย)
# ====================================================
# API สำหรับฝั่ง ADMIN: รายงานยอดขายรวมและสินค้าขายดี (Dashboard Metrics)
@app.get("/api/sales/summary")
def get_sales_summary(
    selected_date: Optional[str] = Query(None, description="รูปแบบวันที่: YYYY-MM-DD"), 
    db: Session = Depends(get_db)):
 
    if selected_date:
        target_date = datetime.datetime.strptime(selected_date, "%Y-%m-%d").date()
    else:
        target_date = datetime.datetime.now(ZoneInfo("Asia/Bangkok")).date()

    # ตั้งเงื่อนไขกรองวันที่โดยแปลงเขตเวลาของฐานข้อมูล (UTC) ให้สัมพันธ์เป็นเวลาไทยปัจจุบัน
    date_filter = func.date(func.timezone('Asia/Bangkok', models.OrderModel.created_at)) == func.date(func.timezone('Asia/Bangkok', target_date))

    # คำนวณรายได้ทั้งหมด (คิดจากทุกออเดอร์ที่มีการจ่ายเงินสำเร็จ)
    # ใช้ func.coalesce ป้องกันไม่ให้ฐานข้อมูลคืนค่าเป็น NULL กรณีที่ร้านยังไม่มีออเดอร์แรก
    total_revenue = db.query(func.sum(models.OrderModel.grandtotal_price))\
                      .filter(date_filter)\
                      .filter(models.OrderModel.status == models.OrderStatus.COMPLETED)\
                      .scalar() or 0.0
                      
    # นับสัดส่วนสถานะของออเดอร์ในคิวห้องครัวปัจจุบัน
    status_counts = db.query(models.OrderModel.status, func.count(models.OrderModel.id))\
                      .filter(date_filter)\
                      .group_by(models.OrderModel.status).all()
                      
    status_distribution = {}
    for status_enum, count in status_counts:
        status_str = status_enum.value if hasattr(status_enum, 'value') else str(status_enum)
        status_distribution[status_str] = count
    
    # จัดอันดับขนม/เครื่องดื่มขายดี 5 อันดับแรก (Top Selling Products)
    top_items = db.query(
        models.OrderItemModel.product_id,
        func.sum(models.OrderItemModel.quantity).label("total_qty")
    ).join(models.OrderModel)\
     .filter(date_filter)\
     .filter(models.OrderModel.status == models.OrderStatus.COMPLETED)\
     .group_by(models.OrderItemModel.product_id)\
     .order_by(func.sum(models.OrderItemModel.quantity).desc()).limit(5).all()
     
    top_products_list = []
    for item in top_items:
        prod = db.query(models.ProductModel).filter(models.ProductModel.id == item.product_id).first()
        if prod:
            top_products_list.append({
                "name": prod.name,
                "qty": int(item.total_qty), # ใช้คีย์สั้น 'qty' เพื่อให้ React นำไปลูปวาดกราฟหรือตารางได้ทันที
                "category": prod.category
            })

    return {
        "total_revenue": float(total_revenue),
        "status_distribution": status_distribution,
        "top_products": top_products_list
    }