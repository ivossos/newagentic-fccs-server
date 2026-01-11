
import sqlite3
import os

def check_db():
    db_path = 'data/fccs_agent.db'
    if not os.path.exists(db_path):
        print(f"Database {db_path} does not exist.")
        return
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print(f"Tables in {db_path}: {tables}")
    
    for table in tables:
        table_name = table[0]
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        print(f"Table {table_name}: {count} rows")
    
    conn.close()

if __name__ == "__main__":
    check_db()

