# fix_trade_dates.py
import psycopg2
from datetime import datetime

conn = psycopg2.connect(
    host="elevizio-prod-db.c6jyosou8fw5.us-east-1.rds.amazonaws.com",
    port=5432,
    database="tradepilotai",
    user="elevizio_admin",
    password="ElevProd2026!Secure"
)
conn.autocommit = True
cursor = conn.cursor()

# Set trade_date from opened_at for grouping
cursor.execute("""
    UPDATE trades 
    SET trade_date = DATE(opened_at)::text,
        status = CASE 
            WHEN exit_price IS NOT NULL THEN 'closed'
            ELSE 'open'
        END,
        closed_at = CASE 
            WHEN exit_price IS NOT NULL AND closed_at IS NULL THEN opened_at
            ELSE closed_at
        END
    WHERE trade_date IS NULL
""")

print(f"✓ Updated {cursor.rowcount} trades with proper dates and status")

# Check results
cursor.execute("""
    SELECT 
        trade_date,
        COUNT(*) as count,
        SUM(CASE WHEN status='closed' THEN 1 ELSE 0 END) as closed,
        ROUND(SUM(COALESCE(pnl, 0))::numeric, 2) as total_pnl
    FROM trades 
    WHERE user_id = 1
    GROUP BY trade_date 
    ORDER BY trade_date DESC 
    LIMIT 10
""")

print("\nTrade summary by date:")
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]} trades, {row[2]} closed, P&L: ${row[3]}")

conn.close()