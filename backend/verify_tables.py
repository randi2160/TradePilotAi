# verify_tables.py
import psycopg2

conn = psycopg2.connect(
    host="elevizio-prod-db.c6jyosou8fw5.us-east-1.rds.amazonaws.com",
    port=5432,
    database="tradepilotai",
    user="elevizio_admin",
    password="ElevProd2026!Secure"
)

cursor = conn.cursor()
cursor.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public'
    ORDER BY table_name;
""")

tables = cursor.fetchall()
print("Tables in database:")
for table in tables:
    print(f"  - {table[0]}")

if not tables:
    print("  No tables found!")

conn.close()