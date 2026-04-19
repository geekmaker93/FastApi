#!/usr/bin/env python3
"""Check if web search is actually working."""

import sys
sys.path.insert(0, 'c:/Users/18606/Desktop/crop_backend')

from app.services.web_search import smart_search
from app.services.product_locator import _get_location_context

# Try a direct web search
print("="*70)
print("TESTING DIRECT WEB SEARCH")
print("="*70)

question = "What is the latest treatment for tomato blight?"
location_context = _get_location_context(40.1726, -80.7369)

print(f"\nQuestion: {question}")
print(f"Location: {location_context}")
print(f"\nCalling smart_search()...")

try:
    results = smart_search(question, location=location_context, num_results=3)
    
    print(f"\nResults received:")
    print(f"  has_results: {results.get('has_results')}")
    print(f"  total_results: {results.get('total_results')}")
    print(f"  search_method: {results.get('search_method')}")
    print(f"  query: {results.get('query')}")
    
    if results.get('has_results') and results.get('results'):
        print(f"\n  Top result:")
        r = results['results'][0]
        print(f"    Title: {r.get('title', 'N/A')[:100]}")
        print(f"    Snippet: {r.get('snippet', 'N/A')[:150]}")
    
except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*70)
