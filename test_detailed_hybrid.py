#!/usr/bin/env python3
"""Detailed test of hybrid data approach showing all response fields."""

import requests
import json

BASE_URL = "http://127.0.0.1:8000"

payload = {
    "question": "What is the latest treatment for tomato blight?",
    "latitude": 40.1726,
    "longitude": -80.7369,
    "backend_data": {
        "farm": {
            "farm_name": "Test Farm",
            "crop_type": "tomato",
            "area_hectares": 2.0
        },
        "weather": {
            "temperature": 22,
            "humidity": 65
        }
    },
    "session_id": "debug-test"
}

print("\n" + "="*70)
print("DETAILED HYBRID APPROACH TEST")
print("="*70)

print(f"\nSending request to {BASE_URL}/ai/ask...")
print(f"Question: {payload['question']}")

try:
    response = requests.post(f"{BASE_URL}/ai/ask", json=payload, timeout=30)
    print(f"\nStatus: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        
        # Show all keys in the response
        print("\n" + "-"*70)
        print("RESPONSE KEYS:")
        print("-"*70)
        for key in sorted(data.keys()):
            print(f"  • {key}")
        
        # Show data strategy details
        print("\n" + "-"*70)
        print("DATA STRATEGY:")
        print("-"*70)
        if "data_strategy" in data:
            for k, v in data["data_strategy"].items():
                print(f"  {k}: {v}")
        else:
            print("  No data_strategy in response")
        
        # Show data analysis if present
        if "data_analysis" in data:
            print("\n" + "-"*70)
            print("DATA ANALYSIS:")
            print("-"*70)
            for k, v in data["data_analysis"].items():
                if k == "internal_quality":
                    print(f"  {k}:")
                    for ik, iv in v.items():
                        print(f"    {ik}: {iv}")
                elif k == "combined_strategy":
                    print(f"  {k}:")
                    for line in v.split("\n"):
                        print(f"    {line}")
                else:
                    print(f"  {k}: {v}")
        
        # Show answer
        print("\n" + "-"*70)
        print("ANSWER:")
        print("-"*70)
        print(f"  {data.get('answer', 'N/A')[:300]}...")
        
        # Show context sources
        if "context_sources" in data:
            print(f"\nContext Sources: {data['context_sources']}")
        
        # Show if external search was used
        if "external_search_results" in data:
            print(f"\nExternal Search Results Found: YES")
        else:
            print(f"\nExternal Search Results Found: NO")
            
    else:
        print(f"Error: {response.status_code}")
        print(f"Response: {response.text[:500]}")
        
except Exception as e:
    print(f"Error: {e}")

print("\n" + "="*70)
print("END OF TEST")
print("="*70)
