# import_data_to_postgres.py (FINAL VERSION)
import json
import psycopg2
from psycopg2.extras import execute_batch

# PostgreSQL connection
conn = psycopg2.connect(
    host="elevizio-prod-db.c6jyosou8fw5.us-east-1.rds.amazonaws.com",
    port=5432,
    database="tradepilotai",
    user="elevizio_admin",
    password="ElevProd2026!Secure"
)
conn.autocommit = True
cursor = conn.cursor()

# Load exported data
with open('export_data.json', 'r') as f:
    data = json.load(f)

print(f"Loaded {len(data['users'])} users, {len(data['trades'])} trades")

# Import users with boolean conversion
if data['users']:
    users_data = []
    for user in data['users']:
        # Map old 'role' to 'is_admin' and convert integers to booleans
        is_admin = bool(user.get('role', 'user') == 'admin')
        is_active = bool(user.get('is_active', 1))  # Convert 0/1 to False/True
        
        users_data.append((
            user['id'],
            user['email'],
            user['hashed_password'],
            is_admin,
            is_active,
            user.get('created_at')
        ))
    
    execute_batch(cursor, """
        INSERT INTO users (id, email, hashed_password, is_admin, is_active, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
    """, users_data)
    print(f"✓ Imported {len(users_data)} users")

# Import trades (UPDATED - timestamp -> opened_at)
if data['trades']:
    trades_data = []
    for trade in data['trades']:
        trades_data.append((
            trade['id'],
            trade['symbol'],
            trade['side'],
            trade['qty'],
            trade['entry_price'],
            trade.get('exit_price'),
            trade.get('pnl', 0),
            trade.get('pnl_pct', 0),
            trade.get('confidence', 0),
            trade.get('timestamp'),  # This will map to opened_at
            trade.get('user_id', 1)
        ))
    
    execute_batch(cursor, """
        INSERT INTO trades (id, symbol, side, qty, entry_price, exit_price, pnl, pnl_pct, confidence, opened_at, user_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
    """, trades_data)
    print(f"✓ Imported {len(trades_data)} trades")

# Update sequences to avoid ID conflicts
cursor.execute("SELECT setval('users_id_seq', (SELECT MAX(id) FROM users));")
cursor.execute("SELECT setval('trades_id_seq', (SELECT MAX(id) FROM trades));")
print("✓ Updated sequences")

conn.close()
print("\n✅ Migration complete!")