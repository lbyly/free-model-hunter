import os

path = 'C:/Users/Administrator/.hermes/hermes-agent'
for root, dirs, files in os.walk(path):
    for dir_name in dirs:
        if 'gateway' in dir_name.lower() or 'tui' in dir_name.lower():
            print("Dir:", os.path.join(root, dir_name))
    for file_name in files:
        if 'gateway' in file_name.lower() or 'tui' in file_name.lower() or 'server' in file_name.lower():
            print("File:", os.path.join(root, file_name))
