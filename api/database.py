# app/database.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 1. เปลี่ยนตรงส่วนเริ่มต้นเป็น postgresql+psycopg
# 2. อย่าลืมตรวจสอบว่า Username (postgres), Password (bhrdKrs0WBB05PGj) 
#    และชื่อฐานข้อมูล (wimuti_bakery) ตรงกับในเครื่องของคุณแล้วจริงๆ นะครับ
# postgresql://postgres.uyissypistylvtzudxmt:[YOUR-PASSWORD]@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres
#host=aws-0-ap-northeast-1.pooler.supabase.com
#port=6543
#database=postgres
#user=postgres.uyissypistylvtzudxmt
# SQLALCHEMY_DATABASE_URL = "postgresql+psycopg://postgres:123456@localhost:5432/wimuti_bakery"

SQLALCHEMY_DATABASE_URL = "postgresql://postgres.uyissypistylvtzudxmt:bhrdKrs0WBB05PGj@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
