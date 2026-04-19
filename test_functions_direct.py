#!/usr/bin/env python3
"""Direct test of hybrid approach functions."""

import sys
sys.path.insert(0, 'c:/Users/18606/Desktop/crop_backend')

from app.services.web_search import (
    should_search_externally,
    evaluate_internal_data_quality,
    combine_internal_and_external,
)

# Test 1: should_search_externally
print("="*70)
print("TEST 1: should_search_externally()")
print("="*70)

questions = [
    "What is the latest treatment for tomato blight?",
    "How much water do tomatoes need?",
    "How to prevent fungal diseases?",
    "Recent news about crop prices",
]

for q in questions:
    result = should_search_externally(q)
    print(f"Question: {q}")
    print(f"Should search externally: {result}\n")

# Test 2: evaluate_internal_data_quality
print("="*70)
print("TEST 2: evaluate_internal_data_quality()")
print("="*70)

backend_data = {
    "farm": {"farm_name": "TestFarm", "crop_type": "tomato"},
    "weather": {"temperature": 22, "humidity": 65},
}

question = "What is the latest treatment for tomato blight?"
quality = evaluate_internal_data_quality(backend_data, question)

print(f"Question: {question}")
print(f"Internal data quality:")
print(f"  Has sufficient data: {quality['has_sufficient_internal_data']}")
print(f"  Confidence: {quality['confidence']:.2f}")
print(f"  Internal sources: {quality['internal_sources']}")
print(f"  Gaps: {quality['gaps']}")
print(f"  Should cross-reference: {quality['should_cross_reference']}")
print(f"  Recommendation: {quality['recommendation']}\n")

# Test 3: combine_internal_and_external
print("="*70)
print("TEST 3: combine_internal_and_external()")
print("="*70)

# Simulate empty external search
external_data = {"has_results": False}
combined = combine_internal_and_external(backend_data, external_data)

print(f"With no external search results:")
print(f"  Primary source: {combined['primary_source']}")
print(f"  Confidence: {combined['confidence']:.2f}")
print(f"  Recommendation: {combined['recommendation']}\n")

# Simulate external search with results
external_data = {
    "has_results": True,
    "search_method": "duckduckgo",
    "query": "tomato blight treatment",
    "results": [
        {
            "title": "Tomato Blight Treatment Guide",
            "snippet": "Latest methods for treating tomato blight...",
            "link": "example.com"
        }
    ]
}

combined = combine_internal_and_external(backend_data, external_data)

print(f"With external search results:")
print(f"  Primary source: {combined['primary_source']}")
print(f"  Confidence: {combined['confidence']:.2f}")
print(f"  Recommendations: {combined['recommendation']}")
print(f"  Combined insights: {combined['combined_insights']}\n")

print("="*70)
print("ALL FUNCTION TESTS COMPLETED SUCCESSFULLY")
print("="*70)
