# fix_historical_trades.py
import psycopg2

conn = psycopg2.connect(
    host="elevizio-prod-db.c6jyosou8fw5.us-east-1.rds.amazonaws.com",
    port=5432,
    database="tradepilotai",
    user="elevizio_admin",
    password="ElevProd2026!Secure"
)
conn.autocommit = True
cursor = conn.cursor()

# Update trades with exit_price to have status='closed' and closed_at
cursor.execute("""
    UPDATE trades 
    SET status = 'closed', 
        closed_at = opened_at 
    WHERE exit_price IS NOT NULL 
    AND status != 'closed'
""")

print(f"✓ Updated {cursor.rowcount} trades to closed status")

conn.close()