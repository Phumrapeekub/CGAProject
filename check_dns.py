import socket
hosts = [
    "db.ylahheyefrqxcjqccpsn.supabase.com",
    "ylahheyefrqxcjqccpsn.supabase.com",
    "db.ylahheyefrqxcjqccpsn.supabase.co",
    "ylahheyefrqxcjqccpsn.supabase.co",
    "aws-1-ap-southeast-1.pooler.supabase.com"
]

for host in hosts:
    try:
        ip = socket.gethostbyname(host)
        print(f"✅ {host} -> {ip}")
    except Exception as e:
        print(f"❌ {host} -> {e}")
