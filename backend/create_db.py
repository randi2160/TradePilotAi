import psycopg2

# Connect to existing RDS
conn = psycopg2.connect(
    host="elevizio-prod-db.c6jyosou8fw5.us-east-1.rds.amazonaws.com",
    port=5432,
    database="postgres",  # Connect to default postgres db to create new one
    user="elevizio_admin",
    password="ElevProd2026!Secure"
)
conn.autocommit = True
cursor = conn.cursor()

# Create new database
try:
    cursor.execute("CREATE DATABASE tradepilotai;")
    print("✓ Database 'tradepilotai' created successfully!")
except Exception as e:
    print(f"Database might already exist: {e}")

conn.close()