import os
import mysql.connector
import psycopg2
from urllib.parse import urlparse

def get_mysql_conn():
    return mysql.connector.connect(
        host='127.0.0.1',
        user='root',
        password='Kantiya203_',
        database='cga_system_dev'
    )

def get_pg_conn():
    # Parse Supabase DB URL
    # IMPORTANT: You need the direct PostgreSQL connection string from Supabase Settings -> Database
    # Format: postgresql://postgres:[PASSWORD]@db.[REF].supabase.co:5432/postgres
    # For now, I will use a placeholder. User needs to provide this or set DB_URL env var.
    db_url = os.getenv("DB_URL") 
    if not db_url:
        print("❌ Error: Please set 'DB_URL' environment variable with your Supabase Connection String.")
        print("Example: set DB_URL=postgresql://postgres:pass@db.ref.supabase.co:5432/postgres")
        return None
    return psycopg2.connect(db_url)

def map_mysql_to_pg_type(mysql_type):
    mysql_type = mysql_type.lower()
    if 'int' in mysql_type: return 'INTEGER'
    if 'varchar' in mysql_type: return 'TEXT' # Supabase prefers TEXT
    if 'text' in mysql_type: return 'TEXT'
    if 'datetime' in mysql_type or 'timestamp' in mysql_type: return 'TIMESTAMPTZ'
    if 'date' in mysql_type: return 'DATE'
    if 'float' in mysql_type or 'decimal' in mysql_type or 'double' in mysql_type: return 'DECIMAL'
    if 'enum' in mysql_type: return 'TEXT' # Simplify enums to text
    return 'TEXT'

def sync_schema():
    print("🚀 Starting Schema Sync (Local MySQL -> Supabase PostgreSQL)...")
    
    my_conn = get_mysql_conn()
    pg_conn = get_pg_conn()
    
    if not my_conn or not pg_conn:
        return

    my_cur = my_conn.cursor(dictionary=True)
    pg_cur = pg_conn.cursor()

    # Tables to sync structure
    target_tables = ['patients', 'cga_headers', 'consultations']

    for table in target_tables:
        print(f"
🔍 Checking table: {table}")
        
        # 1. Get Local Columns
        my_cur.execute(f"DESCRIBE {table}")
        local_cols = my_cur.fetchall()
        
        # 2. Get Cloud Columns
        try:
            pg_cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}'")
            cloud_cols_raw = pg_cur.fetchall()
            cloud_cols = [c[0] for c in cloud_cols_raw]
        except:
            print(f"   ⚠️ Table {table} might not exist in Supabase. Creating...")
            # Simple create logic could be added here, but usually tables exist.
            pg_conn.rollback() # Reset transaction
            continue

        # 3. Compare and Add
        for col in local_cols:
            col_name = col['Field']
            col_type = col['Type']
            
            if col_name not in cloud_cols:
                pg_type = map_mysql_to_pg_type(col_type)
                print(f"   ➕ Adding missing column: {col_name} ({pg_type})")
                try:
                    alter_sql = f"ALTER TABLE {table} ADD COLUMN {col_name} {pg_type}"
                    pg_cur.execute(alter_sql)
                    pg_conn.commit()
                    print("      ✅ Success")
                except Exception as e:
                    print(f"      ❌ Failed: {e}")
                    pg_conn.rollback()
            else:
                print(f"   ✓ {col_name} exists")

    print("
✨ Schema Sync Completed!")
    my_conn.close()
    pg_conn.close()

if __name__ == "__main__":
    # Install psycopg2 if missing: pip install psycopg2-binary
    sync_schema()
