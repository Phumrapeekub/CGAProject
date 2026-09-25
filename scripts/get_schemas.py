import mysql.connector

def get_schemas():
    config = {
        'host': '127.0.0.1',
        'user': 'root',
        'password': 'Kantiya203_',
        'database': 'cga_system_dev'
    }
    tables = ['assessment_mmse', 'assessment_tgds', 'assessment_answers']
    try:
        conn = mysql.connector.connect(**config)
        cur = conn.cursor()
        for table in tables:
            print(f"--- Schema for {table} ---")
            cur.execute(f"DESCRIBE {table}")
            for col in cur.fetchall():
                print(col)
        conn.close()
    except Exception as e:
        print(e)

if __name__ == "__main__":
    get_schemas()