import sqlite3
import os

DB_FILE = "prices.db"

print(f"Looking for DB at: {os.path.abspath(DB_FILE)}")
print(f"File exists: {os.path.exists(DB_FILE)}")

if os.path.exists(DB_FILE):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print(f"Tables found: {tables}")

    cursor.execute("SELECT COUNT(*) FROM prices")
    count = cursor.fetchone()[0]
    print(f"Rows in 'prices' table: {count}")

    cursor.execute("SELECT * FROM prices")
    rows = cursor.fetchall()
    for row in rows:
        print(row)

    conn.close()
else:
    print("prices.db not found in this folder!")
