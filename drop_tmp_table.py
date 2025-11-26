import sqlite3


def drop_tmp_table():
    try:
        conn = sqlite3.connect("cbpos.db")
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS _alembic_tmp_customers")
        conn.commit()
        print("Dropped _alembic_tmp_customers")
        conn.close()
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    drop_tmp_table()
