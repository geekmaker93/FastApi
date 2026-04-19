#!/usr/bin/env python3
"""Test Mistral 7B with a complex agricultural scenario."""

import requests
import json

BASE_URL = "http://127.0.0.1:8000"

print("\n" + "="*70)
print("MISTRAL 7B - COMPLEX SCENARIO TEST")
print("="*70)

# Complex scenario question
payload = {
    "question": "I have a 5-hectare tomato farm with recent NDVI of 0.72 showing some stress in sections near drainage issues. Humidity is 75% and I've noticed early blight symptoms on lower leaves. Temperature is 24°C. What's my priority action plan?",
    "latitude": 40.1726,
    "longitude": -80.7369,
    "backend_data": {
        "farm": {
            "farm_name": "Valley Tomato Farm",
            "crop_type": "tomato",
            "area_hectares": 5.0,
            "ndvi": 0.72,
            "concerns": ["drainage", "early_blight"]
        },
        "weather": {
            "temperature": 24,
            "humidity": 75,
            "rainfall_mm": 0,
            "wind_speed": 5
        },
        "products_available": [
            "fungicide_spray",
            "drainage_tiles",
            "drip_irrigation",
            "neem_oil"
        ]
    },
    "session_id": "mistral-complex-test"
}

print(f"\nScenario: {payload['question'][:100]}...")
print("-"*70)

try:
    response = requests.post(f"{BASE_URL}/ai/ask", json=payload, timeout=60)
    
    if response.status_code == 200:
        data = response.json()
        answer = data.get('answer', 'N/A')
        confidence = data.get('confidence', 0)
        risks = data.get('risks', [])
        actions = data.get('actions', [])
        
        print(f"\n✓ Model: mistral:7b")
        print(f"✓ Confidence: {confidence:.0%}")
        print(f"✓ Response length: {len(answer)} characters ({len(answer.split())} words)")
        
        print(f"\n📋 AI RECOMMENDATION:")
        print(f"\n{answer}")
        
        if risks:
            print(f"\n⚠️ IDENTIFIED RISKS:")
            for risk in risks[:3]:
                print(f"   • {risk}")
        
        if actions:
            print(f"\n✓ RECOMMENDED ACTIONS:")
            for i, action in enumerate(actions[:5], 1):
                print(f"   {i}. {action}")
        else:
            print(f"\n(No structured actions in response)")
        
    else:
        print(f"✗ Error {response.status_code}")
        print(response.text[:300])
        
except Exception as e:
    print(f"✗ Error: {e}")

print("\n" + "="*70)
print("\nCOMPARISON: Mistral 7B vs Qwen 0.5B")
print("="*70)
print("\nQwen 0.5B (397MB):        Mistral 7B (4.4GB):")
print("  • Ultra-light             • 14x larger")
print("  • Quick responses (<1s)    • Thoughtful responses (15-30s)")
print("  • Simple answers           • Complex reasoning")
print("  • Limited context          • Better understanding")
print("  • For simple queries ✓     • For farm management ✓✓✓")
print("\nNote: With hybrid data approach, Mistral FIRST checks farm data,")
print("then validates with web search = most accurate recommendations!")
print("="*70)
