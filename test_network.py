#!/usr/bin/env python3
"""Test network connectivity."""

import requests

print("Testing network connectivity...\n")

endpoints = [
    ("DuckDuckGo API", "https://api.duckduckgo.com/?q=tomato&format=json"),
    ("Wikipedia", "https://en.wikipedia.org/api/rest_v1/page/summary/Tomato"),
    ("Google", "https://www.google.com"),
]

for name, url in endpoints:
    try:
        response = requests.get(url, timeout=5)
        print(f"✓ {name}: Status {response.status_code}")
    except requests.exceptions.Timeout:
        print(f"✗ {name}: Timeout (5s)")
    except requests.exceptions.ConnectionError:
        print(f"✗ {name}: Connection error")
    except Exception as e:
        print(f"✗ {name}: {type(e).__name__}: {e}")
