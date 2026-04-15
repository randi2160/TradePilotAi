# create_tradepilot_db.py
import psycopg2

conn = psycopg2.connect(
    host="elevizio-prod-db.c6jyosou8fw5.us-east-1.rds.amazonaws.com",
    port=5432,
    database="postgres",
    user="elevizio_admin",
    password="ElevProd2026!Secure"
)
conn.autocommit = True
cursor = conn.cursor()

try:
    cursor.execute("CREATE DATABASE tradepilotai;")
    print("✓ Database 'tradepilotai' created!")
except Exception as e:
    print(f"Database creation: {e}")

conn.close()