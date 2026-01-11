import sqlite3
import os

db_path = 'data/fccs_agent.db'
if not os.path.exists(db_path):
    print(f"Database {db_path} not found.")
else:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    try:
        c.execute("SELECT member FROM metadata_cache WHERE member LIKE '%Agent%'")
        rows = c.fetchall()
        print(f"Found {len(rows)} members with 'Agent' in name:")
        for row in rows:
            print(f"  - {row[0]}")
    except sqlite3.OperationalError as e:
        print(f"Error: {e}")
    conn.close()

