"""
Comprehensive test: Create paired yield predictions and farmer reports for full comparison
This demonstrates the complete validation workflow with multiple seasons of data
"""

import requests
from datetime import date, timedelta
import json

API_BASE = "http://127.0.0.1:8000"
FARM_ID = 1

def seed_comparison_data():
    """Create comprehensive paired prediction and actual yield data"""
    
    print("=" * 80)
    print("SEEDING COMPREHENSIVE COMPARISON DATA")
    print("=" * 80)
    
    # 2024 Season - May to October
    print("\n[2024 SEASON] Creating yield predictions and farmer reports...")
    
    predictions_2024 = [
        {"farm_id": FARM_ID, "date": "2024-05-01", "yield_estimate": 4350.0, "notes": "Early season prediction"},
        {"farm_id": FARM_ID, "date": "2024-06-15", "yield_estimate": 4450.0, "notes": "Mid-season update"},
        {"farm_id": FARM_ID, "date": "2024-08-15", "yield_estimate": 4500.0, "notes": "Late season prediction"},
    ]
    
    prediction_ids_2024 = []
    for pred in predictions_2024:
        resp = requests.post(f"{API_BASE}/yields/", json=pred)
        pred_id = resp.json().get('id')
        prediction_ids_2024.append(pred_id)
        print(f"  ✓ Prediction {pred['date']}: {pred['yield_estimate']} kg/ha (ID: {pred_id})")
    
    # Create corresponding farmer reports for 2024
    print("\n  Adding farmer-reported yields for 2024...")
    farmer_reports_2024 = [
        {"farm_id": FARM_ID, "yield_result_id": prediction_ids_2024[0], "date": "2024-05-15", "actual_yield": 4320.0, "notes": "Early assessment"},
        {"farm_id": FARM_ID, "yield_result_id": prediction_ids_2024[1], "date": "2024-06-30", "actual_yield": 4480.0, "notes": "Mid-season harvest"},
        {"farm_id": FARM_ID, "yield_result_id": prediction_ids_2024[2], "date": "2024-09-01", "actual_yield": 4520.0, "notes": "Final harvest"},
    ]
    
    for report in farmer_reports_2024:
        resp = requests.post(f"{API_BASE}/yields/reports/", json=report)
        print(f"  ✓ Farmer report {report['date']}: {report['actual_yield']} kg/ha (linked to prediction)")
    
    # 2025 Season - May to October
    print("\n[2025 SEASON] Creating yield predictions and farmer reports...")
    
    predictions_2025 = [
        {"farm_id": FARM_ID, "date": "2025-05-05", "yield_estimate": 4200.0, "notes": "Early season prediction"},
        {"farm_id": FARM_ID, "date": "2025-06-20", "yield_estimate": 4300.0, "notes": "Mid-season update"},
        {"farm_id": FARM_ID, "date": "2025-08-20", "yield_estimate": 4350.0, "notes": "Late season prediction"},
    ]
    
    prediction_ids_2025 = []
    for pred in predictions_2025:
        resp = requests.post(f"{API_BASE}/yields/", json=pred)
        pred_id = resp.json().get('id')
        prediction_ids_2025.append(pred_id)
        print(f"  ✓ Prediction {pred['date']}: {pred['yield_estimate']} kg/ha (ID: {pred_id})")
    
    # Create corresponding farmer reports for 2025
    print("\n  Adding farmer-reported yields for 2025...")
    farmer_reports_2025 = [
        {"farm_id": FARM_ID, "yield_result_id": prediction_ids_2025[0], "date": "2025-05-20", "actual_yield": 4180.0, "notes": "Early assessment - slightly lower"},
        {"farm_id": FARM_ID, "yield_result_id": prediction_ids_2025[1], "date": "2025-07-05", "actual_yield": 4250.0, "notes": "Mid-season - within range"},
        {"farm_id": FARM_ID, "yield_result_id": prediction_ids_2025[2], "date": "2025-09-05", "actual_yield": 4400.0, "notes": "Final harvest - exceeded!"},
    ]
    
    for report in farmer_reports_2025:
        resp = requests.post(f"{API_BASE}/yields/reports/", json=report)
        print(f"  ✓ Farmer report {report['date']}: {report['actual_yield']} kg/ha (linked to prediction)")
    
    # Add historical baselines
    print("\n[HISTORICAL BASELINES]")
    
    historical = [
        {"farm_id": FARM_ID, "crop_type": "Corn", "year": 2024, "avg_yield": 4400.0, "min_yield": 4000.0, "max_yield": 4800.0, "sample_count": 5},
        {"farm_id": FARM_ID, "crop_type": "Corn", "year": 2025, "avg_yield": 4350.0, "min_yield": 3950.0, "max_yield": 4750.0, "sample_count": 5},
    ]
    
    for hist in historical:
        resp = requests.post(f"{API_BASE}/yields/historical/", json=hist)
        print(f"  ✓ Historical baseline {hist['year']}: {hist['avg_yield']} kg/ha")
    
    print("\n" + "=" * 80)
    print("SEEDING COMPLETE!")
    print("=" * 80)
    
    # Test all comparison endpoints
    print("\nTesting comparison endpoints...")
    
    # 1. Get seasonal comparison
    print("\n[1] SEASONAL COMPARISON")
    resp = requests.get(f"{API_BASE}/yields/farm/{FARM_ID}/comparison?num_seasons=2")
    data = resp.json()
    print(json.dumps(data, indent=2, default=str))
    
    # 2. Get accuracy metrics
    print("\n[2] OVERALL ACCURACY METRICS")
    resp = requests.get(f"{API_BASE}/yields/farm/{FARM_ID}/accuracy")
    print(json.dumps(resp.json(), indent=2, default=str))
    
    # 3. Get correlation
    print("\n[3] NDVI-YIELD CORRELATION")
    resp = requests.get(f"{API_BASE}/yields/farm/{FARM_ID}/ndvi-correlation")
    print(json.dumps(resp.json(), indent=2, default=str))
    
    # 4. Get complete dashboard
    print("\n[4] VALIDATION DASHBOARD")
    resp = requests.get(f"{API_BASE}/yields/farm/{FARM_ID}/validation-dashboard?num_seasons=2")
    data = resp.json()
    print(f"Farm: {data.get('farm_name')}")
    print(f"Crop: {data.get('crop_type')}")
    print(f"Seasons analyzed: {data.get('summary', {}).get('total_seasons_analyzed')}")
    print(f"Average deviation: {data.get('summary', {}).get('avg_deviation_percent')}%")
    print(f"Trends correct: {data.get('summary', {}).get('trends_correct_percent')}%")
    print(json.dumps(data, indent=2, default=str))

if __name__ == "__main__":
    seed_comparison_data()
