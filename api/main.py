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
from sqlalchemy import and_

# สร้างตารางข้อมูลใน PostgreSQL ทันทีที่เปิด Server
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Wimuti Bakery API")

origins =[
    "http://localhost:5173",
    "https://wimuti.vercel.app",
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

# เปิดให้ภายนอกสามารถเข้ามาดึงรูปภาพในโฟลเดอร์ uploads ไปแสดงผลได้
UPLOAD_DIR = "uploads"
app.mount("/static-images", StaticFiles(directory=UPLOAD_DIR), name="static-images")

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

# 👤 API สำหรับฝั่ง USER & ADMIN: ดึงข้อมูลเมนูทั้งหมด
@app.get("/api/products")
def get_all_products(db: Session = Depends(get_db)):
    products = db.query(models.ProductModel).all()
    from fastapi.encoders import jsonable_encoder
    return jsonable_encoder(products)

# API สำหรับฝั่ง ADMIN: เพิ่มเมนูขนมใหม่ POST พร้อมอัปโหลดรูป
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
    if file and file.filename:
        await file.seek(0)
        clean_filename = f"{int(time.time())}_{file.filename.replace(' ', '_')}"
        file_location = f"{UPLOAD_DIR}/{clean_filename}"
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        image_url = f"https://vercel.app{clean_filename}"

    db_product = models.ProductModel(
        name=name, category=category, price=price, pieces=pieces,
        image=image_url, desc=desc if desc else "", is_active=True
    )    
    try:
        db.add(db_product)
        db.commit()
        db.refresh(db_product)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"เกิดข้อผิดพลาด: {str(e)}")

    from fastapi.encoders import jsonable_encoder
    return jsonable_encoder(db_product)
   
# API สำหรับฝั่ง ADMIN: แก้ไขข้อมูลเมนูและราคา PUT
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
    db_product = db.query(models.ProductModel).filter(models.ProductModel.id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="ไม่พบเมนูสินค้านี้ in ระบบ")
    
    image_url = image
    if file and file.filename:
        await file.seek(0)
        clean_filename = f"{int(time.time())}_{file.filename.replace(' ', '_')}"
        file_location = f"{UPLOAD_DIR}/{clean_filename}"
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        image_url = f"http://localhost:8000/static-images/{clean_filename}"

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
        raise HTTPException(status_code=400, detail=f"ไม่สามารถบันทึกข้อมูลแก้ไขได้เนื่องจาก: {str(e)}")        
        
    from fastapi.encoders import jsonable_encoder
    return jsonable_encoder(db_product)

# API สำหรับฝั่ง ADMIN: ลบเมนูออกจากระบบ DELETE
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"ไม่สามารถลบข้อมูลได้เนื่องจาก: {str(e)}")
    return {}

# API สำหรับฝั่ง ADMIN: สลับสถานะ พร้อมขาย หรือ ยกเลิก PATCH
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

class OrderItemCreate(BaseModel):
    product_id: int
    quantity: int

class OrderCreateRequest(BaseModel):
    items: List[OrderItemCreate]
    customer_name: str = ""
    notes: str = ""    
    discount_price: float = 0.0
    payment_method: str = "โอน"

class OrderStatusUpdateRequest(BaseModel):
    status: str

# API สำหรับฝั่ง USER: ส่งออเดอร์ใหม่เข้ามาในระบบ
@app.post("/api/orders", status_code=status.HTTP_201_CREATED)
def create_order(request: OrderCreateRequest, db: Session = Depends(get_db)):
    subtotal_price = 0.0
    order_items_to_add = []
    
    for req_item in request.items:
        product = db.query(models.ProductModel).filter(models.ProductModel.id == req_item.product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"ไม่พบสินค้าไอดี #{req_item.product_id} ในระบบเมนู")
            
        if product.pieces < req_item.quantity:
            raise HTTPException(status_code=400, detail=f"สินค้า '{product.name}' มีสต็อกไม่เพียงพอ")
            
        item_total_price = product.price * req_item.quantity
        subtotal_price += item_total_price
        product.pieces -= req_item.quantity
        
        order_item = models.OrderItemModel(product_id=product.id, quantity=req_item.quantity, price=product.price)
        order_items_to_add.append(order_item)

    discount_amount = request.discount_price
    grandtotal_price = max(0.0, subtotal_price - discount_amount)
    thailand_now = datetime.datetime.now(ZoneInfo("Asia/Bangkok"))

    new_order = models.OrderModel(
        customer_name=request.customer_name, subtotal_price=subtotal_price,
        discount_price=discount_amount, grandtotal_price=grandtotal_price,
        status=models.OrderStatus.PENDING, notes=request.notes,
        payment_method=request.payment_method, created_at=thailand_now, items=order_items_to_add
    )
    try:
        db.add(new_order)
        db.commit()
        db.refresh(new_order)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาดในการบันทึกออเดอร์: {str(e)}")
        
    from fastapi.encoders import jsonable_encoder
    return jsonable_encoder(new_order)

# ฟังก์ชันดึงออเดอร์คิวครัว
@app.get("/api/orders")
def get_all_orders(selected_date: Optional[str] = Query(None, description="YYYY-MM-DD"), db: Session = Depends(get_db)):
    if selected_date:
        end_date = datetime.datetime.strptime(selected_date, "%Y-%m-%d").date()
    else:
        end_date = datetime.datetime.now(ZoneInfo("Asia/Bangkok")).date()

    start_date = end_date - datetime.timedelta(days=7)
    local_order_date = func.date(func.timezone('Asia/Bangkok', models.OrderModel.created_at))

    orders = db.query(models.OrderModel)\
                .options(joinedload(models.OrderModel.items).joinedload(models.OrderItemModel.product))\
                .filter(and_(
                        local_order_date >= start_date,
                        local_order_date <= end_date))\
                .filter(models.OrderModel.status != models.OrderStatus.CANCELLED)\
                .order_by(models.OrderModel.created_at.desc()).all()
               
    result = []
    for order in orders:
        order_dict = {
            "id": order.id, "customer_name": order.customer_name, "subtotal_price": order.subtotal_price,
            "discount_price": order.discount_price, "grandtotal_price": order.grandtotal_price,
            "status": order.status.value if hasattr(order.status, 'value') else order.status,
            "notes": order.notes, "payment_method": order.payment_method, 
            "created_at": order.created_at.isoformat() if order.created_at else None, "items": []  
        }
        for item in order.items:
            item_dict = {
                "id": item.id, "product_id": item.product_id, "quantity": item.quantity, "price": item.price,
                "product": {"id": item.product.id, "name": item.product.name, "price": item.product.price} if item.product else None
            }
            order_dict["items"].append(item_dict)
        result.append(order_dict)

    from fastapi.encoders import jsonable_encoder
    return jsonable_encoder(result)

# อัปเดตสถานะออเดอร์
@app.put("/api/orders/{order_id}/status")
def update_order_status(order_id: int, request: OrderStatusUpdateRequest, db: Session = Depends(get_db)):
    order = db.query(models.OrderModel).filter(models.OrderModel.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="ไม่พบรายการออเดอร์นี้ในคิว")
        
    current_status_str = order.status.value if hasattr(order.status, 'value') else str(order.status)
    if current_status_str in ["สำเร็จ", "ยกเลิก"]:
        raise HTTPException(status_code=400, detail="ไม่สามารถเปลี่ยนสถานะออเดอร์ที่สิ้นสุดแล้วได้")
    
    matched_status = None
    for enum_item in models.OrderStatus:
        if enum_item.value == request.status:
            matched_status = enum_item
            break           
    if not matched_status:
        raise HTTPException(status_code=422, detail="สถานะไม่สอดคล้องกับระเบียบ")

    if (request.status == "ยกเลิก" or matched_status == models.OrderStatus.CANCELLED) and order.status != matched_status:
        for item in order.items:
            product = db.query(models.ProductModel).filter(models.ProductModel.id == item.product_id).first()
            if product: product.pieces += item.quantity  
            
    order.status = matched_status
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"ไม่สามารถเปลี่ยนสถานะได้: {str(e)}")        
    return {}

# API สำหรับฝั่ง ADMIN: รายงานยอดขายรวมและสินค้าขายดี
@app.get("/api/sales/summary")
def get_sales_summary(selected_date: Optional[str] = Query(None, description="YYYY-MM-DD"), db: Session = Depends(get_db)):
    if selected_date:
        target_date = datetime.datetime.strptime(selected_date, "%Y-%m-%d").date()
    else:
        target_date = datetime.datetime.now(ZoneInfo("Asia/Bangkok")).date()

    date_filter = func.date(func.timezone('Asia/Bangkok', models.OrderModel.created_at)) == func.date(func.timezone('Asia/Bangkok', target_date))

    total_revenue = db.query(func.sum(models.OrderModel.grandtotal_price)).filter(date_filter).filter(models.OrderModel.status == models.OrderStatus.COMPLETED).scalar() or 0.0
    total_cash = db.query(func.sum(models.OrderModel.grandtotal_price)).filter(date_filter).filter(models.OrderModel.status == models.OrderStatus.COMPLETED).filter(models.OrderModel.payment_method == models.OrderPayment.CASH).scalar() or 0.0 
    total_transfer = db.query(func.sum(models.OrderModel.grandtotal_price)).filter(date_filter).filter(models.OrderModel.status == models.OrderStatus.COMPLETED).filter(models.OrderModel.payment_method == models.OrderPayment.TRANSFER).scalar() or 0.0
          
    status_counts = db.query(models.OrderModel.status, func.count(models.OrderModel.id)).filter(date_filter).group_by(models.OrderModel.status).all()
                      
    status_distribution = {}
    for status_enum, count in status_counts:
        status_str = status_enum.value if hasattr(status_enum, 'value') else str(status_enum)
        status_distribution[status_str] = count
    
    top_items = db.query(models.OrderItemModel.product_id, func.sum(models.OrderItemModel.quantity).label("total_qty")).join(models.OrderModel).filter(date_filter).filter(models.OrderModel.status == models.OrderStatus.COMPLETED).group_by(models.OrderItemModel.product_id).order_by(func.sum(models.OrderItemModel.quantity).desc()).limit(5).all()
     
    top_products_list = []
    for item in top_items:
        prod = db.query(models.ProductModel).filter(models.ProductModel.id == item.product_id).first()
        if prod:
            top_products_list.append({"name": prod.name, "qty": int(item.total_qty), "category": prod.category})

    return {
        "total_revenue": float(total_revenue), "total_cash": float(total_cash), "total_transfer": float(total_transfer),
        "status_distribution": status_distribution, "top_products": top_products_list
    }

# API สำหรับอัปเดตแก้ไขรายการออเดอร์เดิมจากตะกร้า
@app.put("/api/orders/{order_id}")
def update_existing_order(order_id: int, request: OrderCreateRequest, db: Session = Depends(get_db)):
    order = db.query(models.OrderModel).filter(models.OrderModel.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="ไม่พบรายการออเดอร์ใบนี้ในระบบ")

    current_status_str = order.status.value if hasattr(order.status, 'value') else str(order.status)
    if current_status_str in ["สำเร็จ", "ยกเลิก"]:
        raise HTTPException(status_code=400, detail="ไม่สามารถแก้ไขออเดอร์ใบนี้ได้แล้ว")

    # คืนสต็อกชั่วคราว
    for old_item in order.items:
        product = db.query(models.ProductModel).filter(models.ProductModel.id == old_item.product_id).first()
        if product: product.pieces += old_item.quantity

    # ลบแถวย่อยเดิม
    db.query(models.OrderItemModel).filter(models.OrderItemModel.order_id == order_id).delete()

    subtotal_price = 0.0
    order_items_to_add = []

    # คำนวณใหม่และตัดสต็อกจริง
    for req_item in request.items:
        product = db.query(models.ProductModel).filter(models.ProductModel.id == req_item.product_id).first()
        if not product: raise HTTPException(status_code=404, detail="ไม่พบสินค้าในคลัง")
            
        if product.pieces < req_item.quantity:
            raise HTTPException(status_code=400, detail="จำนวนสต็อกหลังแก้ไขไม่เพียงพอ")
            
        subtotal_price += product.price * req_item.quantity
        product.pieces -= req_item.quantity
        
        order_item = models.OrderItemModel(order_id=order.id, product_id=product.id, quantity=req_item.quantity, price=product.price)
        order_items_to_add.append(order_item)

    discount_amount = request.discount_price
    grandtotal_price = max(0.0, subtotal_price - discount_amount)

    order.customer_name = request.customer_name
    order.subtotal_price = subtotal_price
    order.discount_price = discount_amount
    order.grandtotal_price = grandtotal_price
    order.notes = request.notes
    order.payment_method = request.payment_method
    order.items = order_items_to_add 

    try:
        db.commit()
        db.refresh(order)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาดในการบันทึกอัปเดต: {str(e)}")
        
    from fastapi.encoders import jsonable_encoder
    return jsonable_encoder(order)
