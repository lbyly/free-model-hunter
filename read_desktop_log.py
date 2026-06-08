import os

path = r'C:\Users\Administrator\AppData\Local\hermes\logs\desktop.log'
if not os.path.exists(path):
    print("File does not exist")
else:
    print(f"File size: {os.path.getsize(path)} bytes")
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            print("Content length:", len(content))
            lines = content.splitlines()
            print("Lines count:", len(lines))
            for line in lines[-150:]:
                print(line.encode('ascii', errors='replace').decode('ascii'))
    except Exception as e:
        print("Error:", e)
