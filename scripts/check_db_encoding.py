import sqlite3
import json

def check_db_encoding():
    db_path = 'data/fccs_agent.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    tables = ['conversation_context', 'query_history', 'result_cache', 'tool_executions']
    
    for table in tables:
        print(f"\nChecking table: {table}")
        try:
            cursor.execute(f"SELECT * FROM {table}")
            rows = cursor.fetchall()
            for row in rows:
                for val in row:
                    if isinstance(val, str):
                        try:
                            val.encode('utf-8')
                        except UnicodeEncodeError:
                            print(f"Found non-UTF8 string in {table}: {val}")
                    elif isinstance(val, bytes):
                        try:
                            val.decode('utf-8')
                        except UnicodeDecodeError as e:
                            print(f"Found non-UTF8 bytes in {table}: {val[:50]}... Error: {e}")
        except Exception as e:
            print(f"Error checking {table}: {e}")
            
    conn.close()

if __name__ == "__main__":
    check_db_encoding()
