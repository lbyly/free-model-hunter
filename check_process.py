import psutil
import socket

print("=== Running Processes ===")
for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
    try:
        name = proc.info['name'] or ''
        cmdline = proc.info['cmdline'] or []
        cmd_str = ' '.join(cmdline)
        if 'hermes' in name.lower() or 'python' in name.lower() or 'uvicorn' in name.lower() or 'agent' in name.lower():
            print(f"PID: {proc.info['pid']} | Name: {name} | Cmd: {cmd_str}")
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

print("\n=== Listening TCP Ports ===")
for conn in psutil.net_connections(kind='inet'):
    if conn.status == 'LISTEN':
        print(f"Laddr: {conn.laddr} | Status: {conn.status} | PID: {conn.pid}")
