import os
import json
import datetime
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
load_dotenv()

# Initialize Supabase client
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

if not url or not key:
    print("❌ Error: SUPABASE_URL or SUPABASE_KEY not found in .env file.")
    exit(1)

try:
    supabase: Client = create_client(url, key)
except Exception as e:
    print(f"❌ Error connecting to Supabase: {e}")
    exit(1)

def fetch_table_data(table_name, limit=5):
    """Fetches the latest data from a Supabase table."""
    try:
        print(f"📥 Fetching data from table: {table_name}...")
        # Assuming most tables have an 'id' or 'created_at' to sort by. 
        # If not, it just takes any 5 rows.
        response = supabase.table(table_name).select("*").order("id", desc=True).limit(limit).execute()
        return response.data
    except Exception as e:
        print(f"   ⚠️ Error fetching {table_name}: {e}")
        return []

def json_serializer(obj):
    """Helper to serialize datetime objects for JSON."""
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    return str(obj)

def main():
    print("🚀 Starting Supabase Debug Hook...")
    
    debug_data = {
        "timestamp": datetime.datetime.now().isoformat(),
        "tables": {}
    }

    # List of tables to inspect
    target_tables = ["patients", "encounters", "cga_headers", "consultations"]

    for table in target_tables:
        rows = fetch_table_data(table)
        debug_data["tables"][table] = rows
        print(f"   ✅ Retrieved {len(rows)} rows from {table}")

    # Save to JSON file
    output_filename = "supabase_debug_dump.json"
    try:
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(debug_data, f, ensure_ascii=False, indent=4, default=json_serializer)
        print(f"
✨ Debug data successfully saved to: {output_filename}")
        print("   You can inspect this file to see exactly what data is currently in Supabase.")
    except Exception as e:
        print(f"
❌ Error saving JSON file: {e}")

if __name__ == "__main__":
    main()
