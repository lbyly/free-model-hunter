import os
import sys

# Set standard output encoding to ascii/ignore or utf-8 if supported to prevent UnicodeEncodeErrors in Windows consoles
try:
    reconfig = getattr(sys.stdout, 'reconfigure', None)
    if reconfig is not None:
        reconfig(encoding='utf-8')
except AttributeError:
    pass

paths = [
    'C:/Users/Administrator/.hermes/logs/agent.log',
    'C:/Users/Administrator/.hermes/logs/errors.log',
    'C:/Users/Administrator/.hermes/logs/gateway.log',
    'C:/Users/Administrator/AppData/Local/hermes/logs/agent.log',
    'C:/Users/Administrator/AppData/Local/hermes/logs/errors.log',
    'C:/Users/Administrator/AppData/Local/hermes/logs/desktop.log',
    'C:/Users/Administrator/AppData/Local/hermes/logs/gateway.log'
]

print("--- FILE SIZES ---")
for p in paths:
    if os.path.exists(p):
        print(f"{p}: {os.path.getsize(p)} bytes")
    else:
        print(f"{p}: Does not exist")

print("\n--- ERROR SEARCH ---")
for p in paths:
    if os.path.exists(p):
        print(f"\nScanning {p}:")
        with open(p, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        matches = []
        for i, line in enumerate(lines):
            line_lower = line.lower()
            if any(k in line_lower for k in ['free-model-hub', 'fmh-', 'plugin', 'exception', 'traceback', 'error']):
                matches.append((i+1, line.strip()))
        
        if not matches:
            print("  No matches found.")
        else:
            print(f"  Found {len(matches)} matches. Showing last 30 matches:")
            for idx, text in matches[-30:]:
                # Use ascii with question marks to be completely safe from encoding errors
                safe_text = text[:160].encode('ascii', errors='replace').decode('ascii')
                print(f"    Line {idx}: {safe_text}")
