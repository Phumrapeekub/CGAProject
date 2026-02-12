import mysql.connector

def generate_fix_sql():
    config = {
        'host': '127.0.0.1',
        'user': 'root',
        'password': 'Kantiya203_',
        'database': 'cga_system_dev'
    }
    
    # Map MySQL types to PostgreSQL compatible types
    type_map = {
        'int': 'INTEGER',
        'bigint': 'BIGINT',
        'varchar': 'TEXT',
        'text': 'TEXT',
        'datetime': 'TIMESTAMPTZ',
        'timestamp': 'TIMESTAMPTZ',
        'date': 'DATE',
        'float': 'DECIMAL',
        'double': 'DECIMAL',
        'decimal': 'DECIMAL',
        'enum': 'TEXT', # Simplify enums to text for compatibility
        'tinyint': 'BOOLEAN' # Often used for boolean
    }

    try:
        conn = mysql.connector.connect(**config)
        cur = conn.cursor(dictionary=True)
        
        # Tables we care about syncing
        tables = ['patients', 'cga_headers', 'consultations']
        
        sql_statements = []
        sql_statements.append("-- Run this in Supabase SQL Editor to fix missing columns")
        
        for table in tables:
            print(f"Scanning table: {table}...")
            try:
                cur.execute(f"DESCRIBE {table}")
                columns = cur.fetchall()
                
                for col in columns:
                    fname = col['Field']
                    ftype = col['Type'].split('(')[0] # Grab base type
                    
                    pg_type = type_map.get(ftype, 'TEXT')
                    
                    # Create generic ADD COLUMN IF NOT EXISTS logic (Postgres doesn't support IF NOT EXISTS in ADD COLUMN directly in all versions easily without DO block, but we can use a simple ALTER)
                    # We will generate simple ALTER statements. Supabase will error if exists but that's fine (safe fail).
                    
                    sql = f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {fname} {pg_type};"
                    sql_statements.append(sql)
                    
            except Exception as e:
                print(f"Skipping {table} (Not found locally?): {e}")

        # Write to file
        with open("fix_supabase_schema.sql", "w", encoding="utf-8") as f:
            f.write("\n".join(sql_statements))
            
        print("\n✅ Generated 'fix_supabase_schema.sql' successfully!")
        print("👉 Please open this file, copy the content, and run it in Supabase SQL Editor.")
        
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    generate_fix_sql()