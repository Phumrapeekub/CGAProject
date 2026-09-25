import os
from dotenv import load_dotenv
load_dotenv()

from supabase import create_client, Client

_supabase_client: Client | None = None

def get_supabase_client() -> Client:
    """
    Returns a cached Supabase client.
    Requires SUPABASE_URL and SUPABASE_KEY to be set in environment variables.
    """
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables")

    _supabase_client = create_client(url, key)
    return _supabase_client

get_db_client = get_supabase_client

def get_db_connection():
    """
    Safe stub: MySQL is deprecated in this project (Supabase only).
    Always returns None to bypass legacy fallback branches safely.
    """
    return None
