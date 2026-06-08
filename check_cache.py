import json
import os

cache_path = 'C:/Users/Administrator/AppData/Local/hermes/provider_models_cache.json'
if os.path.exists(cache_path):
    print(f"--- {cache_path} keys ---")
    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print("Keys:", list(data.keys()))
        if 'providers' in data:
            print("Providers in cache:", [p.get('name') or p.get('slug') for p in data['providers']])
        else:
            # Maybe it's a dict of provider_slug -> models
            print("Top level keys (slugs):", list(data.keys()))
    except Exception as e:
        print("Error reading cache:", e)
else:
    print(f"{cache_path} does not exist")

print("\n--- PLUGIN DISCOVERY LOGS ---")
agent_log = 'C:/Users/Administrator/AppData/Local/hermes/logs/agent.log'
if os.path.exists(agent_log):
    with open(agent_log, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if 'plugin' in line.lower() and ('free-model-hub' in line.lower() or 'fmh-' in line.lower()):
                print(line.strip())
            elif 'plugin discovery complete' in line.lower():
                print(line.strip())
