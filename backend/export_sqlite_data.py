# export_sqlite_data.py
import sqlite3
import json

def export_data(db_path='autotrader.db'):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    data = {
        'users': [],
        'trades': [],
        'settings': []
    }
    
    # Export users
    cursor.execute("SELECT * FROM users")
    for row in cursor.fetchall():
        data['users'].append(dict(row))
    
    # Export trades
    cursor.execute("SELECT * FROM trades")
    for row in cursor.fetchall():
        data['trades'].append(dict(row))
    
    # Export settings (if exists)
    try:
        cursor.execute("SELECT * FROM settings")
        for row in cursor.fetchall():
            data['settings'].append(dict(row))
    except:
        pass
    
    conn.close()
    
    with open('export_data.json', 'w') as f:
        json.dump(data, f, indent=2, default=str)
    
    print(f"✓ Exported {len(data['users'])} users, {len(data['trades'])} trades, {len(data['settings'])} settings")

if __name__ == "__main__":
    export_data()