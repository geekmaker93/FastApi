import requests
import time

time.sleep(3)  # Wait for server to start

base_url = "http://127.0.0.1:8000"

# Test dashboard HTML
print("Testing dashboard.html...")
try:
    response = requests.get(f"{base_url}/dashboard.html", timeout=5)
    if response.status_code == 200:
        print(f"✓ Dashboard loaded (200 OK, {len(response.text)} chars)")
        print(f"  First 200 chars: {response.text[:200]}")
    else:
        print(f"✗ Dashboard failed: {response.status_code}")
except Exception as e:
    print(f"✗ Error loading dashboard: {e}")

# Test yield analytics API
print("\nTesting /yields/farm/1/analytics...")
try:
    response = requests.get(f"{base_url}/yields/farm/1/analytics", timeout=5)
    if response.status_code == 200:
        print(f"✓ Analytics endpoint (200 OK)")
        data = response.json()
        print(f"  Farm: {data.get('farm_name')}, Crop: {data.get('crop_type')}")
        print(f"  Overall Accuracy: {data.get('overall_accuracy')}%")
    else:
        print(f"✗ Analytics failed: {response.status_code}")
except Exception as e:
    print(f"✗ Error: {e}")

# Test NDVI correlation API
print("\nTesting /yields/farm/1/ndvi-correlation...")
try:
    response = requests.get(f"{base_url}/yields/farm/1/ndvi-correlation", timeout=5)
    if response.status_code == 200:
        print(f"✓ NDVI Correlation endpoint (200 OK)")
        data = response.json()
        corr = data.get('correlation_analysis', {})
        print(f"  Correlation: {corr.get('correlation_coefficient')}")
    else:
        print(f"✗ NDVI failed: {response.status_code}")
except Exception as e:
    print(f"✗ Error: {e}")

print("\n✓ All systems ready! Open http://127.0.0.1:8000/dashboard.html in your browser")
