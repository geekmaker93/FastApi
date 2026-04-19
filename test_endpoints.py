#!/usr/bin/env python3
"""Test if chart/satellite API endpoints are working."""

import requests

BASE_URL = "http://127.0.0.1:8000"

endpoints = [
    ("Tile Sources", "/sentinel/tile-sources"),
    ("ESRI World", "/sentinel/external/esri-world"),
    ("NASA GIBS", "/sentinel/external/nasa-gibs"),
    ("Yields Analytics", "/yields/farm/1/analytics"),
    ("NDVI Correlation", "/yields/farm/1/ndvi-correlation"),
    ("Validation Dashboard", "/yields/farm/1/validation-dashboard"),
]

print("\n" + "="*70)
print("TESTING CHART/DATA ENDPOINTS")
print("="*70)

for name, endpoint in endpoints:
    try:
        response = requests.get(f"{BASE_URL}{endpoint}", timeout=5)
        status = response.status_code
        
        if status == 200:
            data = response.json()
            print(f"\n✓ {name}")
            print(f"  Status: {status}")
            print(f"  Response keys: {list(data.keys())[:5]}" if isinstance(data, dict) else f"  Type: {type(data)}")
            if isinstance(data, dict) and len(str(data)) > 200:
                print(f"  Size: {len(str(data))} chars")
            else:
                print(f"  Data: {str(data)[:200]}")
        else:
            print(f"\n✗ {name}")
            print(f"  Status: {status}")
            print(f"  Response: {response.text[:150]}")
    except Exception as e:
        print(f"\n✗ {name}")
        print(f"  Error: {e}")

print("\n" + "="*70)
print("CHECKING NDVI IMAGE")
print("="*70)

img_path = "mobile_app/ndvi_map.png"
import os
if os.path.exists(img_path):
    size = os.path.getsize(img_path)
    print(f"✓ {img_path}")
    print(f"  Size: {size} bytes")
else:
    print(f"✗ {img_path} NOT FOUND")

print("\n" + "="*70)
