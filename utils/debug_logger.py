import json
import datetime
import os

LOG_FILE = "supabase_payload_log.json"

def log_supabase_payload(table: str, data: dict, method: str):
    """
    Appends the payload data to a JSON log file.
    """
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "table": table,
        "method": method,
        "payload": data
    }
    
    # Read existing logs
    logs = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                content = f.read()
                if content:
                    logs = json.loads(content)
        except Exception as e:
            print(f"⚠️ Error reading log file: {e}")

    # Append new entry
    logs.append(entry)

    # Write back to file
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
        print(f"🐛 [Debug Hook] Payload logged to {LOG_FILE}")
    except Exception as e:
        print(f"❌ Error writing log file: {e}")
