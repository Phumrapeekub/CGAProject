import os
import sys
from waitress import serve
from dotenv import load_dotenv

load_dotenv()
from app import app

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    host = os.getenv("HOST", "0.0.0.0")
    threads = int(os.getenv("THREADS", 8))
    
    print("=" * 65)
    print("   🏥 CGA HOSPITAL SYSTEM - PRODUCTION WSGI SERVER (WAITRESS)")
    print(f"   📡 Serving on http://{host}:{port}")
    print(f"   ⚙️  Worker Threads: {threads}")
    print("   🚀 Multi-threaded production server is ready to accept requests.")
    print("=" * 65)
    
    serve(app, host=host, port=port, threads=threads)
