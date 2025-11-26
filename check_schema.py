import sqlite3


def check_schema():
    try:
        conn = sqlite3.connect("pos.db")
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(customers)")
        columns = cursor.fetchall()
        for col in columns:
            print(col)
        conn.close()
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    check_schema()
