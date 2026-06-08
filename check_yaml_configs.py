import yaml

def inspect_config(path):
    print(f"\n=== Inspecting {path} ===")
    try:
        with open(path, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f)
        
        custom_provs = cfg.get("custom_providers", [])
        print(f"Number of custom_providers: {len(custom_provs)}")
        for i, entry in enumerate(custom_provs[:10]):
            name = entry.get("name")
            base_url = entry.get("base_url")
            model = entry.get("model")
            print(f"  {i}: name='{name}', base_url='{base_url}', model='{model}'")
        if len(custom_provs) > 10:
            print(f"  ... and {len(custom_provs) - 10} more")
            
        provs = cfg.get("providers", {})
        print(f"Providers key count: {len(provs)}")
        print(f"Providers keys: {list(provs.keys())}")
        
    except Exception as e:
        print("Error:", e)

inspect_config('C:/Users/Administrator/.hermes/config.yaml')
inspect_config('C:/Users/Administrator/AppData/Local/hermes/config.yaml')
