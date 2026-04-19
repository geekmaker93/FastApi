#!/usr/bin/env python3
"""Test individual search functions."""

import sys
sys.path.insert(0, 'c:/Users/18606/Desktop/crop_backend')

from app.services.web_search import (
    search_duckduckgo,
    fetch_wikipedia_summary,
)

print("="*70)
print("TEST 1: DuckDuckGo Search")
print("="*70)

query = "tomato blighttomatofungicide treatment"
print(f"\nQuerying DuckDuckGo for: {query}")

try:
    results = search_duckduckgo(query, num_results=3)
    print(f"Results: {len(results)}")
    for i, r in enumerate(results, 1):
        print(f"\n{i}. {r.get('title', 'N/A')}")
        print(f"   Snippet: {r.get('snippet', 'N/A')[:100]}")
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*70)
print("TEST 2: Wikipedia Search")
print("="*70)

topic = "Tomato blight"
print(f"\nQuerying Wikipedia for: {topic}")

try:
    result = fetch_wikipedia_summary(topic)
    if result:
        print(f"✓ Found Wikipedia article")
        print(f"  Title: {result.get('title', 'N/A')}")
        print(f"  Summary: {result.get('summary', 'N/A')[:150]}...")
    else:
        print(f"✗ No Wikipedia article found")
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*70)
