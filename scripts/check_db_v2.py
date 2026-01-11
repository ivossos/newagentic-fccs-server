
import sqlite3
import os

def check_db():
    db_path = 'data/fccs_agent.db'
    if not os.path.exists(db_path):
        print(f"File {db_path} does not exist.")
        return
    
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [t[0] for t in c.fetchall()]
    print(f"Database: {db_path}")
    print(f"Tables found: {tables}")
    
    for table in tables:
        try:
            c.execute(f"SELECT COUNT(*) FROM {table}")
            count = c.fetchone()[0]
            print(f"  {table}: {count} rows")
        except Exception as e:
            print(f"  Error reading {table}: {e}")
    conn.close()

if __name__ == "__main__":
    check_db()

