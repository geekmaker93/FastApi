#!/usr/bin/env python3
"""Test the hybrid data approach for AI recommendations."""

import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000"

def test_latest_treatment():
    """Test with a question needing external search."""
    print("\n" + "="*70)
    print("TEST 1: Latest treatment for tomato blight (needs external search)")
    print("="*70)
    
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
        "session_id": "test-hybrid-latest-treatment"
    }
    
    try:
        print(f"Sending request to {BASE_URL}/ai/ask...")
        response = requests.post(f"{BASE_URL}/ai/ask", json=payload, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Request succeeded (Status: {response.status_code})")
            print(f"\nData Strategy:")
            print(f"  Internal Confidence: {data.get('data_strategy', {}).get('internal_confidence', 'N/A')}")
            print(f"  Primary Source: {data.get('data_strategy', {}).get('primary_source', 'N/A')}")
            print(f"  External Search Used: {data.get('data_strategy', {}).get('external_search', False)}")
            print(f"\nAnswer (first 250 chars):")
            answer = data.get('answer', 'N/A')
            print(f"  {answer[:250]}{'...' if len(answer) > 250 else ''}")
            return True
        else:
            print(f"✗ Request failed (Status: {response.status_code})")
            print(f"Response: {response.text[:500]}")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_watering_question():
    """Test with a question that has sufficient internal data."""
    print("\n" + "="*70)
    print("TEST 2: Watering question (sufficient internal data)")
    print("="*70)
    
    payload = {
        "question": "How much water do tomatoes need per week?",
        "latitude": 40.1726,
        "longitude": -80.7369,
        "backend_data": {
            "farm": {
                "farm_name": "Test Farm",
                "crop_type": "tomato",
                "area_hectares": 2.0
            },
            "products_available": ["drip_irrigation", "soil_moisture_sensor"],
            "weather": {
                "temperature": 22,
                "humidity": 65,
                "rainfall_mm": 5.0
            }
        },
        "session_id": "test-hybrid-watering"
    }
    
    try:
        print(f"Sending request to {BASE_URL}/ai/ask...")
        response = requests.post(f"{BASE_URL}/ai/ask", json=payload, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Request succeeded (Status: {response.status_code})")
            print(f"\nData Strategy:")
            print(f"  Internal Confidence: {data.get('data_strategy', {}).get('internal_confidence', 'N/A')}")
            print(f"  Primary Source: {data.get('data_strategy', {}).get('primary_source', 'N/A')}")
            print(f"  External Search Used: {data.get('data_strategy', {}).get('external_search', False)}")
            print(f"\nAnswer (first 250 chars):")
            answer = data.get('answer', 'N/A')
            print(f"  {answer[:250]}{'...' if len(answer) > 250 else ''}")
            return True
        else:
            print(f"✗ Request failed (Status: {response.status_code})")
            print(f"Response: {response.text[:500]}")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_disease_question():
    """Test with a disease/pest question that might need external search."""
    print("\n" + "="*70)
    print("TEST 3: How to prevent fungal diseases (cross-reference worthy)")
    print("="*70)
    
    payload = {
        "question": "How to prevent fungal diseases on my crops?",
        "latitude": 40.1726,
        "longitude": -80.7369,
        "backend_data": {
            "farm": {
                "farm_name": "Test Farm",
                "crop_type": "tomato",
                "area_hectares": 2.0
            },
            "products_available": ["fungicide_spray", "sulfur", "neem_oil"],
            "weather": {
                "temperature": 22,
                "humidity": 85,
                "rainfall_mm": 25.0
            }
        },
        "session_id": "test-hybrid-fungal"
    }
    
    try:
        print(f"Sending request to {BASE_URL}/ai/ask...")
        response = requests.post(f"{BASE_URL}/ai/ask", json=payload, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Request succeeded (Status: {response.status_code})")
            print(f"\nData Strategy:")
            print(f"  Internal Confidence: {data.get('data_strategy', {}).get('internal_confidence', 'N/A')}")
            print(f"  Primary Source: {data.get('data_strategy', {}).get('primary_source', 'N/A')}")
            print(f"  External Search Used: {data.get('data_strategy', {}).get('external_search', False)}")
            print(f"\nAnswer (first 250 chars):")
            answer = data.get('answer', 'N/A')
            print(f"  {answer[:250]}{'...' if len(answer) > 250 else ''}")
            return True
        else:
            print(f"✗ Request failed (Status: {response.status_code})")
            print(f"Response: {response.text[:500]}")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


if __name__ == "__main__":
    print("\n" + "="*70)
    print("HYBRID DATA APPROACH TEST SUITE")
    print("="*70)
    
    results = []
    results.append(("Test 1: Latest treatment", test_latest_treatment()))
    time.sleep(2)  # Brief pause between tests
    
    results.append(("Test 2: Watering question", test_watering_question()))
    time.sleep(2)
    
    results.append(("Test 3: Fungal diseases", test_disease_question()))
    
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")
    
    total_passed = sum(1 for _, p in results if p)
    print(f"\nTotal: {total_passed}/{len(results)} tests passed")
    print("="*70)
