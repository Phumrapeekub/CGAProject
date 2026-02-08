import os
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def check_supabase_connection() -> dict:
    """
    Attempts to connect to Supabase and performs a basic check.
    Returns a dictionary indicating the connection status and any error messages.
    """
    supabase_url: str = os.getenv("SUPABASE_URL")
    supabase_key: str = os.getenv("SUPABASE_KEY")

    if not supabase_url:
        return {"status": "error", "message": "SUPABASE_URL environment variable not set."}
    if not supabase_key:
        return {"status": "error", "message": "SUPABASE_KEY environment variable not set."}

    try:
        # Initialize Supabase client
        supabase: Client = create_client(supabase_url, supabase_key)

        # For a more robust check, you might attempt a simple query to a public table.
        # Example:
        # response = supabase.from_('your_public_table_name').select('*').limit(1).execute()
        # if response.data is not None:
        #     return {"status": "success", "message": "Successfully connected to Supabase and performed a test query."}
        # else:
        #     return {"status": "error", "message": f"Supabase client initialized but test query failed: {response.error}"}

        # For now, just successful client initialization is considered a basic check.
        return {"status": "success", "message": "Successfully initialized Supabase client. Remember to run 'pip install supabase-py' first."}

    except Exception as e:
        return {"status": "error", "message": f"Failed to connect to Supabase: {e}"}

if __name__ == "__main__":
    # Example of how to run this check directly
    result = check_supabase_connection()
    print(f"Supabase Connection Check: {result['status'].upper()}")
    print(f"Message: {result['message']}")
