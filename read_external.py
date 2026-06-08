import sys

if len(sys.argv) < 2:
    print("Usage: python read_external.py <path> [start_line] [num_lines]")
    sys.exit(1)

path = sys.argv[1]
start_line = int(sys.argv[2]) if len(sys.argv) > 2 else 1
num_lines = int(sys.argv[3]) if len(sys.argv) > 3 else 100

try:
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    
    total = len(lines)
    print(f"--- {path} (lines {start_line}-{min(start_line+num_lines-1, total)} of {total}) ---")
    for idx in range(start_line - 1, min(start_line - 1 + num_lines, total)):
        print(f"{idx+1:4d} | {lines[idx]}", end='')
except Exception as e:
    print("Error:", e)
