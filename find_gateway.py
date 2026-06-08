import os

def search_files(dir_path, query):
    matches = []
    for root, dirs, files in os.walk(dir_path):
        for file in files:
            if file.endswith('.py') or file.endswith('.js') or file.endswith('.ts'):
                p = os.path.join(root, file)
                try:
                    with open(p, 'r', encoding='utf-8', errors='ignore') as f:
                        for idx, line in enumerate(f):
                            if query in line:
                                matches.append((p, idx + 1, line.strip()))
                except Exception:
                    pass
    return matches

print("--- SEARCH FOR list_authenticated_providers ---")
res = search_files('C:/Users/Administrator/.hermes/hermes-agent', 'list_authenticated_providers')
for r in res[:50]:
    print(f"{r[0]}:{r[1]}: {r[2][:150]}")

print("\n--- SEARCH FOR list_picker_providers ---")
res = search_files('C:/Users/Administrator/.hermes/hermes-agent', 'list_picker_providers')
for r in res[:50]:
    print(f"{r[0]}:{r[1]}: {r[2][:150]}")
