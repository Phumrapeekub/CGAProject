import os
import mysql.connector
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash
import re

# Load environment variables
load_dotenv()

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "cga_system_dev")

def clean_sql(sql):
    # 1. Remove comments
    sql = re.sub(r'--.*', '', sql)
    # 2. Remove USE statements
    sql = re.sub(r'(?i)USE\s+[`\w]+;', '', sql)
    return sql

def execute_sql_file(cursor, file_path):
    print(f"Executing: {file_path}")
    with open(file_path, 'r', encoding='utf-8') as f:
        sql = f.read()
    
    sql = clean_sql(sql)
    statements = sql.split(';')
    
    for statement in statements:
        stmt = statement.strip()
        if stmt:
            try:
                cursor.execute(stmt)
                # Consume results if any (important for SELECTs in scripts)
                while cursor.nextset():
                    pass
                if cursor.description:
                    cursor.fetchall()
            except mysql.connector.Error as err:
                if err.errno == 1007: # ER_DB_CREATE_EXISTS
                    continue
                if "016_legacy_admin_users" in file_path and err.errno in [1146, 1054]:
                    continue
                print(f"Error in {file_path}: {err}")

def setup():
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            use_pure=True
        )
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return

    cursor = conn.cursor(buffered=True)

    print(f"Creating database: {DB_NAME}")
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME} DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    cursor.execute(f"USE {DB_NAME}")

    try:
        cursor.execute("SET NAMES 'utf8mb4' COLLATE 'utf8mb4_unicode_ci'")
    except:
        pass

    # 1. Run Baseline Schema
    execute_sql_file(cursor, 'db/01_schema.sql')
    conn.commit()

    # 2. Run Migrations
    migrations_dir = 'db/migrations'
    migration_files = sorted([f for f in os.listdir(migrations_dir) if f.endswith('.sql')])
    
    admin_password_hash = generate_password_hash('password123')

    for filename in migration_files:
        path = os.path.join(migrations_dir, filename)
        
        if '014_seed_admin' in filename:
            print(f"Injecting hash into: {path}")
            with open(path, 'r', encoding='utf-8') as f:
                sql = f.read()
            sql = sql.replace("'<PUT_HASH_HERE>'", f"'{admin_password_hash}'")
            sql = clean_sql(sql)
            statements = sql.split(';')
            for stmt in statements:
                s = stmt.strip()
                if s:
                    cursor.execute(s)
                    while cursor.nextset():
                        pass
                    if cursor.description:
                        cursor.fetchall()
        else:
            execute_sql_file(cursor, path)
        
        conn.commit()

    print("\n✅ Database setup complete!")
    print(f"Admin User: admin / password123")
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    setup()
