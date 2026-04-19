import requests
import json
import time

base_url = "http://127.0.0.1:8000"

print("Testing API endpoints...\n")

# Test health
print("1. Testing /health...")
try:
    response = requests.get(f"{base_url}/health", timeout=5)
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        print(f"   ✓ Response: {response.json()}")
    else:
        print(f"   ✗ Failed")
except Exception as e:
    print(f"   ✗ Error: {e}")

# Test news endpoint
print("\n2. Testing /news/...")
try:
    response = requests.get(f"{base_url}/news/", timeout=10)
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   ✓ Got {data.get('total_articles', 0)} articles")
        if data.get('articles'):
            print(f"   First article: {data['articles'][0].get('title', 'N/A')[:60]}")
    else:
        print(f"   ✗ Error: {response.text[:200]}")
except Exception as e:
    print(f"   ✗ Error: {e}")

# Test yields
print("\n3. Testing /yields/farm/1/analytics...")
try:
    response = requests.get(f"{base_url}/yields/farm/1/analytics", timeout=5)
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   ✓ Farm: {data.get('farm_name')}, Crop: {data.get('crop_type')}")
    else:
        print(f"   ✗ Error: {response.text}")
except Exception as e:
    print(f"   ✗ Error: {e}")

print("\n" + "="*60)
print("Summary: Check which endpoints are failing above")
print("="*60)
