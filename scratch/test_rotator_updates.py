import os
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.services.rotator import LLMRotator

print("=== Starting rotator updates verification ===")

config_file = Path(__file__).resolve().parent.parent / "scratch" / "models_config.json"

# Remove existing config to start fresh
if config_file.exists():
    os.remove(config_file)
    print("Removed existing models_config.json")

print("\n--- 1. Initializing LLMRotator (this should perform the initial check) ---")
rotator = LLMRotator()

# Check if config file was created
if config_file.exists():
    print(f"✅ models_config.json was created at {config_file}")
    with open(config_file, "r") as f:
        config_data = json.load(f)
    print(f"Current last_checked_date: {config_data.get('last_checked_date')}")
    print("Current models:")
    for k, v in config_data.get("models", {}).items():
        print(f"  {k} -> {v}")
else:
    print("❌ Error: models_config.json was NOT created!")
    sys.exit(1)

print("\n--- 2. Simulating outdated/missing models in config ---")
with open(config_file, "r") as f:
    config_data = json.load(f)

# Change Cloudflare model to a fake name that doesn't exist
cf_key = "cloudflare::@cf/meta/llama-3.1-8b-instruct"
if cf_key in config_data["models"]:
    print(f"Corrupting cloudflare model: {config_data['models'][cf_key]} -> @cf/meta/llama-3.1-8b-instruct-FAKE")
    config_data["models"][cf_key] = "@cf/meta/llama-3.1-8b-instruct-FAKE"

# Change Cerebras model to a fake name that doesn't exist
cerebras_key = "cerebras::llama3.1-8b"
if cerebras_key in config_data["models"]:
    print(f"Corrupting cerebras model: {config_data['models'][cerebras_key]} -> llama3.1-8b-FAKE")
    config_data["models"][cerebras_key] = "llama3.1-8b-FAKE"

# Save the corrupted config
with open(config_file, "w") as f:
    json.dump(config_data, f, indent=2)

print("\n--- 3. Running check_and_update_models(force=True) to detect and fix corrupted models ---")
rotator.check_and_update_models(force=True)

# Read the updated config and verify replacements
with open(config_file, "r") as f:
    updated_data = json.load(f)

print("\n--- 4. Verification Results ---")
all_passed = True

if cf_key in updated_data["models"]:
    new_cf = updated_data["models"][cf_key]
    if "FAKE" not in new_cf:
        print(f"✅ Cloudflare model was successfully updated to: {new_cf}")
    else:
        print(f"❌ Cloudflare model was NOT updated! Still: {new_cf}")
        all_passed = False

if cerebras_key in updated_data["models"]:
    new_cerebras = updated_data["models"][cerebras_key]
    if "FAKE" not in new_cerebras:
        print(f"✅ Cerebras model was successfully updated to: {new_cerebras}")
    else:
        print(f"❌ Cerebras model was NOT updated! Still: {new_cerebras}")
        all_passed = False

if all_passed:
    print("\n🎉 ALL TESTS PASSED SUCCESSFULLY! Dynamic model checking and updating is working perfectly.")
else:
    print("\n❌ SOME TESTS FAILED.")
    sys.exit(1)
