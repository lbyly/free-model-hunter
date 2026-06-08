import sys
sys.path.insert(0, 'C:/Users/Administrator/.hermes/hermes-agent')

# Load the environment
from hermes_cli.env_loader import load_hermes_dotenv
from pathlib import Path
load_hermes_dotenv(hermes_home=Path('C:/Users/Administrator/.hermes'))

# Discover providers
from providers import _discover_providers, list_providers
_discover_providers()
print("Registered provider names in registry:", [p.name for p in list_providers()])

# Call the build_models_payload
from hermes_cli.inventory import build_models_payload, load_picker_context
ctx = load_picker_context()
print("\nPicker Context:")
print("  current_provider:", ctx.current_provider)
print("  current_model:", ctx.current_model)
print("  custom_providers count:", len(ctx.custom_providers))

payload = build_models_payload(
    ctx,
    include_unconfigured=True,
    picker_hints=True,
    canonical_order=True,
    pricing=False,
    capabilities=False,
    max_models=50,
)

print("\nPayload providers count:", len(payload['providers']))
for p in payload['providers']:
    # Show user-defined and fmh providers
    if p.get('is_user_defined') or 'fmh' in p['slug']:
        print(f"Slug: {p['slug']}, Name: {p['name']}, Authenticated: {p['authenticated']}, is_user_defined: {p.get('is_user_defined')}, Models: {p['models']}")
