#!/usr/bin/env python3
"""Update ollama.py to use mistral:7b instead of qwen2.5:0.5b"""

import re

FILE_PATH = 'app/routes/ollama.py'
OLD_MODEL = 'qwen2.5:0.5b'
NEW_MODEL = 'mistral:7b'

print("="*70)
print(f"UPDATING MODEL FROM {OLD_MODEL} TO {NEW_MODEL}")
print("="*70)

try:
    with open(FILE_PATH, 'r') as f:
        content = f.read()
    
    # Count occurrences
    count = content.count(f'"{OLD_MODEL}"')
    print(f"\nFound {count} occurrences of '{OLD_MODEL}'")
    
    # Replace
    updated = content.replace(f'"{OLD_MODEL}"', f'"{NEW_MODEL}"')
    
    # Write back
    with open(FILE_PATH, 'w') as f:
        f.write(updated)
    
    print(f"✓ Updated {count} references to '{NEW_MODEL}'")
    print("\nNEXT STEPS:")
    print("1. Kill FastAPI server (if running)")
    print("2. Run: .\\\.venv\\Scripts\\python.exe -m uvicorn main:app --reload")
    print("3. Test with: .\\\.venv\\Scripts\\python.exe test_new_model.py")
    print("\nExpect:")
    print("- Much better reasoning and recommendations")
    print("- Longer, more detailed responses")
    print("- Slower (2-5 seconds vs <1 second) but worth it!")
    
except Exception as e:
    print(f"✗ Error: {e}")
