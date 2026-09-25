import json
import datetime
import os

LOG_FILE = "supabase_payload_log.json"
ENABLE_DEBUG_LOGGING = os.getenv("ENABLE_DEBUG_LOGGING", "").lower() in ["1", "true"]

def log_supabase_payload(table: str, data: dict, method: str):
    """
    Safely logs payload data to a JSON log file only when ENABLE_DEBUG_LOGGING is enabled.
    Rotates to keep at most the last 100 entries to prevent memory/disk exhaustion.
    """
    if not ENABLE_DEBUG_LOGGING:
        return

    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "table": table,
        "method": method,
        "payload": data
    }
    
    logs = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                content = f.read()
                if content:
                    logs = json.loads(content)
        except Exception as e:
            print(f"⚠️ Error reading log file: {e}")

    logs.append(entry)
    # Cap to last 100 entries
    if len(logs) > 100:
        logs = logs[-100:]

    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"❌ Error writing log file: {e}")
