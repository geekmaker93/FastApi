#!/usr/bin/env python3
"""Check if Mistral 7B download is complete and ready to use."""

import subprocess
import sys
import time

print("="*70)
print("CHECKING MISTRAL 7B DOWNLOAD STATUS")
print("="*70)

while True:
    try:
        result = subprocess.run(
            ["ollama", "list"],
            text=True,
            capture_output=True,
            timeout=5
        )
        
        output = result.stdout
        
        if "mistral:7b" in output:
            print("\n✓ MISTRAL 7B IS READY!")
            print("\nAvailable models:")
            print(output)
            print("\nNext step: Run update_model.py to switch to mistral:7b")
            sys.exit(0)
        else:
            print("⏳ Mistral 7B still downloading...")
            print("Current models:")
            print(output)
            print("\nWaiting... (check again in 30 seconds)")
            time.sleep(30)
            
    except Exception as e:
        print(f"Error checking status: {e}")
        print("Retrying in 30 seconds...")
        time.sleep(30)
