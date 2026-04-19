#!/usr/bin/env python3
"""Test the new Mistral 7B model and compare with qwen2.5."""

import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000"

test_questions = [
    "What is the best fertilizer for tomatoes with high nitrogen needs?",
    "How do I detect and treat early blight on potato crops?",
    "What's the optimal spacing and irrigation schedule for corn?",
]

print("\n" + "="*70)
print("TESTING MISTRAL 7B MODEL")
print("="*70)

for i, question in enumerate(test_questions, 1):
    print(f"\n[Test {i}/3] Question: {question}")
    print("-"*70)
    
    payload = {
        "question": question,
        "latitude": 40.1726,
        "longitude": -80.7369,
        "backend_data": {
            "farm": {
                "farm_name": "Test Farm",
                "crop_type": "potato" if "potato" in question.lower() else "tomato" if "tomato" in question.lower() else "corn",
                "area_hectares": 5.0
            },
            "weather": {
                "temperature": 22,
                "humidity": 65,
                "rainfall_mm": 15.0
            }
        },
        "session_id": f"test-mistral-{i}"
    }
    
    try:
        start = time.time()
        response = requests.post(
            f"{BASE_URL}/ai/ask",
            json=payload,
            timeout=30
        )
        elapsed = time.time() - start
        
        if response.status_code == 200:
            data = response.json()
            answer = data.get('answer', 'N/A')
            confidence = data.get('confidence', 0)
            
            print(f"✓ Response received in {elapsed:.1f}s")
            print(f"  Confidence: {confidence:.0%}")
            print(f"\n  Answer ({len(answer)} chars):")
            print(f"  {answer}")
            
            # Word count
            word_count = len(answer.split())
            print(f"\n  [Detail level: {word_count} words - {'Very detailed' if word_count > 100 else 'Moderate detail' if word_count > 50 else 'Brief'}]")
        else:
            print(f"✗ Error {response.status_code}: {response.text[:200]}")
            
    except Exception as e:
        print(f"✗ Request failed: {e}")
    
    if i < len(test_questions):
        time.sleep(2)  # Brief pause between tests

print("\n" + "="*70)
print("QUALITY COMPARISON")
print("="*70)
print("\nExpected improvements with Mistral 7B vs Qwen 0.5B:")
print("  • 14x larger model (7B vs 0.5B parameters)")
print("  • Better understanding of agricultural/technical questions")
print("  • More detailed and nuanced recommendations")
print("  • Better reasoning about complex crop scenarios")
print("  • Longer, more helpful responses")
print("\nTrade-off:")
print("  • Slightly slower (2-5s vs <1s, but more valuable)")
print("  • Uses more memory (works fine on CPU)")
print("\n" + "="*70)
