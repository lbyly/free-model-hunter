import psutil

print("=== Listening Ports and Processes ===")
for conn in psutil.net_connections(kind='inet'):
    if conn.status == 'LISTEN':
        try:
            p = psutil.Process(conn.pid)
            port = getattr(conn.laddr, 'port', None)
            if port is None and isinstance(conn.laddr, tuple) and len(conn.laddr) > 1:
                port = list(conn.laddr)[1]
            print(f"Port {port if port is not None else 0:5d} | PID {conn.pid:5d} | {p.name()} | {' '.join(p.cmdline())}")
        except Exception as e:
            port = getattr(conn.laddr, 'port', None)
            if port is None and isinstance(conn.laddr, tuple) and len(conn.laddr) > 1:
                port = list(conn.laddr)[1]
            print(f"Port {port if port is not None else 0:5d} | PID {conn.pid:5d} | <Error: {e}>")
